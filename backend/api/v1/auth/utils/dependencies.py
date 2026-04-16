# api/v1/auth/utils/dependencies.py
# Drop-in replacement with device caching + correct timing instrumentation
from fastapi import Depends, Request, HTTPException, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, bindparam, update
import secrets
import time
import hashlib
from typing import Optional, Dict, Tuple

from database.main.core.session import get_async_session
from database.main.core.models import User
from database.security.core.models import UserDevice
from database.security.core.session import get_security_session, AsyncSession, AsyncSessionLocal

from api.v1.auth.utils.security import decode_access_token
from api.v1.auth.utils.device import hash_device, DEVICE_COOKIE

from utilities.common.common_utility import debug_print

from utilities.common.retries import retry_db
from utilities.common.timing import Timer


# ============================================================
# CONFIG
# ============================================================
_CACHE_TTL = 3.0  # seconds (short-lived safe cache for token->user)
_MAX_CACHE_SIZE = 2048

_JWT_TTL = 2.0  # seconds - ultra-short-lived decoded JWT cache

# Device validation cache (reduces pressure on security DB)
_DEVICE_CACHE_TTL = 60.0  # seconds
_device_cache: Dict[Tuple[int, str], float] = {}  # (user_id, device_hash) -> ts

# Token / user micro-caches
_jwt_cache: Dict[str, Tuple[float, dict]] = {}
_user_cache: Dict[str, Tuple[float, int, User]] = {}  # token_hash -> (ts, user_id, user_obj)


# ============================================================
# INTERNAL CACHE HELPERS
# ============================================================
def _token_key(token: str) -> str:
    """Stable SHA256 token key (never store raw JWT)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _cache_cleanup():
    """Bound cache size + remove expired entries."""
    now = time.monotonic()

    # Expire user cache
    for k, (ts, _, _) in list(_user_cache.items()):
        if now - ts > _CACHE_TTL:
            _user_cache.pop(k, None)

    # Expire jwt cache
    for k, (ts, _) in list(_jwt_cache.items()):
        if now - ts > _JWT_TTL:
            _jwt_cache.pop(k, None)

    # Expire device cache
    for k, ts in list(_device_cache.items()):
        if now - ts > _DEVICE_CACHE_TTL:
            _device_cache.pop(k, None)

    # Hard cap protection
    if len(_user_cache) > _MAX_CACHE_SIZE:
        _user_cache.clear()

    if len(_jwt_cache) > _MAX_CACHE_SIZE:
        _jwt_cache.clear()


def _cache_set_user(token: str, user: User):
    if len(_user_cache) > _MAX_CACHE_SIZE:
        _cache_cleanup()
    _user_cache[_token_key(token)] = (time.monotonic(), user.id, user)


def _cache_get_user(token: str) -> Optional[User]:
    entry = _user_cache.get(_token_key(token))
    if not entry:
        return None

    ts, _, user = entry
    if time.monotonic() - ts > _CACHE_TTL:
        _user_cache.pop(_token_key(token), None)
        return None

    return user


def _cache_remove_token(token: str):
    _user_cache.pop(_token_key(token), None)


def _cache_remove_user(user_id: int):
    for k, (_, uid, _) in list(_user_cache.items()):
        if uid == user_id:
            _user_cache.pop(k, None)


def _device_cache_get(user_id: int, device_hash: str) -> bool:
    key = (user_id, device_hash)
    ts = _device_cache.get(key)
    if not ts:
        return False
    if time.monotonic() - ts > _DEVICE_CACHE_TTL:
        _device_cache.pop(key, None)
        return False
    return True


def _device_cache_set(user_id: int, device_hash: str) -> None:
    # trim if necessary
    if len(_device_cache) > _MAX_CACHE_SIZE:
        _cache_cleanup()
    _device_cache[(user_id, device_hash)] = time.monotonic()


# ============================================================
# JWT MICRO CACHE (HOT PATH)
# ============================================================
def _decode_token_cached(token: str) -> dict:
    """
    Decode JWT with ultra-short TTL caching.
    Huge win when frontend spams /me or multiple calls.
    """
    key = _token_key(token)
    entry = _jwt_cache.get(key)

    if entry:
        ts, payload = entry
        if time.monotonic() - ts <= _JWT_TTL:
            return payload

    payload = decode_access_token(token)
    _jwt_cache[key] = (time.monotonic(), payload)
    return payload


# ============================================================
# PRECOMPILED SQL STATEMENTS
# ============================================================
UID = bindparam("uid")
DH = bindparam("dh")
UNAME = bindparam("uname")

# Trusted device lookup (security DB)
DEVICE_LOOKUP_STMT = (
    select(UserDevice)
    .where(
        UserDevice.user_id == UID,
        UserDevice.device_hash == DH,
        UserDevice.is_revoked.is_(False),
    )
    .limit(1)
)

# Username exists check
USERNAME_EXISTS_STMT = (
    select(User.id)
    .where(User.username == UNAME)
    .limit(1)
)


# ============================================================
# AUTH DEPENDENCY: CURRENT USER
# ============================================================
@retry_db
async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    security_session: AsyncSession = Depends(get_security_session),
) -> User:
    """
    Ultra-hot dependency. Instrumented and optimized:
      - micro-caches for JWT + token->user
      - device validation cache to avoid security DB on hot paths
    """
    t = Timer(f"auth:get_current_user:{request.client.host if request else 'local'}")

    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    t.step("token_read")

    # Fast-path: user cache hit
    cached = _cache_get_user(token)
    if cached:
        t.finish("cache_hit")
        return cached

    # Keep cache bounded during heavy load
    if len(_user_cache) > 512 or len(_jwt_cache) > 512:
        _cache_cleanup()

    # Decode token (cached)
    try:
        payload = _decode_token_cached(token)
        user_id = int(payload["sub"])
        token_device_hash = payload["did"]
    except Exception:
        # decoding failure => unauthorized
        raise HTTPException(status_code=401, detail="Invalid session")
    t.step("jwt_decode")

    # Device cookie binding
    device_secret = request.cookies.get(DEVICE_COOKIE)
    if not device_secret:
        raise HTTPException(status_code=401, detail="Session device missing")

    current_device_hash = hash_device(device_secret)

    if token_device_hash != current_device_hash:
        raise HTTPException(
            status_code=401,
            detail="Session bound to another device",
        )

    # ---------- user fetch (DB #1) ----------
    user = await session.get(User, user_id)
    t.step("user_pk_lookup")

    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not user.is_activated:
        raise HTTPException(
            status_code=403,
            detail="Activate your account to continue",
        )

    if user.is_banned:
        raise HTTPException(status_code=403, detail="Account banned")

    # ---------- device validation (security DB) ----------
    # Check device cache first to avoid hitting security DB on hot paths
    if not _device_cache_get(user.id, current_device_hash):
        device = await security_session.scalar(
            DEVICE_LOOKUP_STMT,
            {"uid": user.id, "dh": current_device_hash},
        )
        t.step("trusted_device_lookup")
        if not device:
            raise HTTPException(status_code=401, detail="Unauthorized")
        # cache positive validation
        _device_cache_set(user.id, current_device_hash)
    else:
        # mark the step even when cached so timings reflect the logical step
        t.step("trusted_device_lookup_cached")

    # ---------- cache + return ----------
    _cache_set_user(token, user)
    t.finish("done")
    return user

async def get_current_user_admin_core(
    request: Request,
    session: AsyncSession,
) -> User:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=404)

    cached = _cache_get_user(token)
    if cached:
        return cached

    if len(_user_cache) > 512 or len(_jwt_cache) > 512:
        _cache_cleanup()

    try:
        payload = _decode_token_cached(token)
        user_id = int(payload["sub"])
    except Exception:
        raise HTTPException(status_code=404)

    user = await session.get(User, user_id)

    if not user:
        raise HTTPException(status_code=404)

    if not user.is_activated:
        raise HTTPException(status_code=404)

    if user.is_banned:
        raise HTTPException(status_code=404)

    _cache_set_user(token, user)
    return user


# ============================================================
# OPTIONAL CURRENT USER
# ============================================================
async def get_current_user_optional(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    security_session: AsyncSession = Depends(get_security_session),
) -> Optional[User]:
    try:
        return await get_current_user(request, session, security_session)
    except HTTPException as e:
        if e.status_code == status.HTTP_401_UNAUTHORIZED:
            return None
        raise


# ============================================================
# USERNAME GENERATION
# ============================================================
def generate_username() -> str:
    return f"user_{secrets.token_hex(4)}"


async def allocate_unique_username(
    session: AsyncSession = Depends(get_async_session),
) -> str:
    """
    Generate usernames until one is unused.
    Uses compiled existence query.
    """
    while True:
        candidate = generate_username()

        exists = await session.scalar(
            USERNAME_EXISTS_STMT,
            {"uname": candidate},
        )

        if not exists:
            return candidate


# ============================================================
# EMAIL MASKING
# ============================================================
def mask_email(email: str) -> str:
    name, domain = email.split("@")

    if len(name) <= 2:
        return name[0] + "***@" + domain

    return name[0] + "***" + name[-1] + "@" + domain


# ============================================================
# DEVICE BINDING
# ============================================================

UID = bindparam("uid")
DID = bindparam("did")

async def revoke_device_by_id(
    *,
    device_id: int,
    user_id: int,
    session: Optional[AsyncSession] = None,
    access_token: Optional[str] = None,
) -> None:
    owns_session = session is None
    if owns_session:
        session = AsyncSessionLocal()

    try:
        device = await session.scalar(
            select(UserDevice).where(
                UserDevice.id == device_id,
                UserDevice.user_id == user_id,
                UserDevice.is_revoked.is_(False),
            )
        )

        if not device:
            raise HTTPException(404, "Device not found")

        device.is_revoked = True
        await session.commit()

        if access_token:
            # your cache removal function
            try:
                _cache_remove_token(access_token)
            except Exception:
                debug_print("Failed to remove token from cache", tag="DEVICE", color="yellow")

    except Exception:
        if owns_session:
            await session.rollback()
        raise
    finally:
        if owns_session:
            await session.close()


async def revoke_all_other_devices(
    *,
    user_id: int,
    current_device_secret: str = "",
    session: Optional[AsyncSession] = None,
) -> None:
    owns_session = session is None
    if owns_session:
        session = AsyncSessionLocal()

    try:
        current_hash = hash_device(current_device_secret or "")

        await session.execute(
            update(UserDevice)
            .where(
                UserDevice.user_id == user_id,
                UserDevice.device_hash != current_hash,
                UserDevice.is_revoked.is_(False),
            )
            .values(is_revoked=True)
        )
        await session.commit()

        # cache-side effect
        try:
            _cache_remove_user(user_id)
        except Exception:
            debug_print("Failed to _cache_remove_user", tag="DEVICE", color="yellow")

    except Exception as e:
        if owns_session:
            await session.rollback()
        debug_print(f"revoke_all_other_devices error: {e}", tag="DEVICE", color="red")
        raise
    finally:
        if owns_session:
            await session.close()


async def revoke_all_devices(
    *,
    user_id: int,
    session: Optional[AsyncSession] = None,
) -> None:
    owns_session = session is None
    if owns_session:
        session = AsyncSessionLocal()

    try:
        await session.execute(
            update(UserDevice)
            .where(
                UserDevice.user_id == user_id,
                UserDevice.is_revoked.is_(False),
            )
            .values(is_revoked=True)
        )
        await session.commit()
        _cache_remove_user(user_id)

    except Exception:
        if owns_session:
            await session.rollback()
        raise
    finally:
        if owns_session:
            await session.close()