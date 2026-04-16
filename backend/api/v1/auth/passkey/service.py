# api/v1/auth/passkey/service.py

from typing import Dict, Any
from datetime import datetime, timezone
from time import time
from enum import Enum
import base64
import os

from fastapi import HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete, update, or_

from webauthn import (
    generate_registration_options as webauthn_generate_registration_options,
    verify_registration_response,
    generate_authentication_options as webauthn_generate_authentication_options,
    verify_authentication_response,
)
from webauthn.helpers.structs import PublicKeyCredentialDescriptor

from database.security.core.models import PasskeyCredential, UserDevice
from database.main.core.models import User, AuthIdentity

from api.v1.auth.utils.device import get_or_create_device_secret, hash_device
from api.v1.auth.utils.security import create_access_token
from api.v1.auth.utils.device_store import register_or_update_device

from utilities.common.common_utility import debug_print

# ─────────────────────────────
# Config
# ─────────────────────────────

if os.getenv("ENV", "local") == "local":
    RP_ID = "localhost"
    ORIGIN = "http://localhost:5173"
else:
    RP_ID = "forkit-frontend.onrender.com"
    ORIGIN = "https://forkit-frontend.onrender.com"

RP_NAME = "Forkit"
CHALLENGE_TTL = 60  # seconds


# ─────────────────────────────
# Helpers
# ─────────────────────────────

def _b64decode(val: str) -> bytes:
    try:
        padding = "=" * (-len(val) % 4)
        return base64.urlsafe_b64decode(val + padding)
    except Exception:
        raise HTTPException(400, "Invalid base64 encoding in credential")


def _bytes_to_b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _snake_to_camel(s: str) -> str:
    parts = s.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _normalize(obj: Any) -> Any:
    if isinstance(obj, (bytes, bytearray, memoryview)):
        return _bytes_to_b64url(bytes(obj))
    if isinstance(obj, Enum):
        return obj.value
    if obj is None or isinstance(obj, (str, bool, int, float)):
        return obj
    if isinstance(obj, dict):
        return {k: _normalize(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, (list, tuple, set)):
        return [_normalize(v) for v in obj]
    if hasattr(obj, "dict"):
        return _normalize(obj.dict())
    if hasattr(obj, "model_dump"):
        return _normalize(obj.model_dump())
    if hasattr(obj, "__dict__"):
        return _normalize(vars(obj))
    return str(obj)


def _rename_keys_to_camel(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            (_snake_to_camel(k) if "_" in k and not any(c.isupper() for c in k) else k): _rename_keys_to_camel(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_rename_keys_to_camel(i) for i in obj]
    return obj


def _webauthn_to_dict(obj: Any) -> Dict[str, Any]:
    normalized = _normalize(obj)
    camelized = _rename_keys_to_camel(normalized)

    user = camelized.get("user")
    if isinstance(user, dict) and "displayName" not in user:
        user["displayName"] = user.get("name") or str(user.get("id", "user"))

    return camelized


# In-memory challenge cache (Redis in prod)
_challenge_cache: dict[str, tuple[bytes, float]] = {}


def _store_challenge(key: str, challenge: bytes) -> None:
    _challenge_cache[key] = (challenge, time() + CHALLENGE_TTL)


def _pop_challenge(key: str) -> bytes | None:
    data = _challenge_cache.pop(key, None)
    if not data:
        return None
    challenge, expires = data
    if time() > expires:
        return None
    return challenge


# ─────────────────────────────
# Registration
# ─────────────────────────────

async def generate_registration_options(user: User, security_session: AsyncSession) -> Dict[str, Any]:
    try:
        challenge = os.urandom(32)
        _store_challenge(f"reg:{user.id}", challenge)

        options = webauthn_generate_registration_options(
            rp_id=RP_ID,
            rp_name=RP_NAME,
            user_id=str(user.id).encode(),
            user_name=user.username,
            challenge=challenge,
            timeout=CHALLENGE_TTL * 1000,
        )

        return _webauthn_to_dict(options)
    except Exception:
        raise HTTPException(500, "Failed to generate passkey registration options")

async def verify_registration(
    attestation: Dict[str, Any],
    user: User,
    security_session: AsyncSession,
    label: str
) -> None:
    challenge = _pop_challenge(f"reg:{user.id}")
    if not challenge:
        raise HTTPException(400, "Registration challenge expired")

    try:
        verification = verify_registration_response(
            credential=attestation,
            expected_challenge=challenge,
            expected_rp_id=RP_ID,
            expected_origin=ORIGIN,
            require_user_verification=True,
        )
    except Exception:
        raise HTTPException(400, "Passkey registration could not be verified")

    existing = await security_session.execute(
        select(PasskeyCredential).where(
            PasskeyCredential.user_id == user.id,
            PasskeyCredential.label == label
        )
    )

    if existing.scalar_one_or_none():
        raise HTTPException(400, "Please choose different label for your passkey, one already exists with this name")

    cred = PasskeyCredential(
        user_id=user.id,
        credential_id=verification.credential_id,
        public_key=verification.credential_public_key,
        sign_count=verification.sign_count,
        aaguid=str(verification.aaguid) if verification.aaguid else None,
        transports=attestation.get("transports"),
        created_at=datetime.now(timezone.utc),
        label=label,
    )

    security_session.add(cred)
    await security_session.commit()


# ─────────────────────────────
# Login
# ─────────────────────────────

async def _resolve_user_id_fast(identifier: str, main_session: AsyncSession) -> int | None:
    ident = identifier.lower()

    user_id = await main_session.scalar(
        select(User.id).where(func.lower(User.username) == ident).limit(1)
    )
    if user_id:
        return user_id

    return await main_session.scalar(
        select(User.id)
        .where(
            or_(
                func.lower(AuthIdentity.provider_user_id) == ident,
                func.lower(User.email) == ident,
            )
        )
        .limit(1)
    )


async def generate_login_options(
    identifier: str,
    security_session: AsyncSession,
    main_session: AsyncSession,
) -> Dict[str, Any]:
    user_id = await _resolve_user_id_fast(identifier, main_session)
    if not user_id:
        raise HTTPException(404, "No passkeys registered for this account")

    creds = (await security_session.execute(
        select(PasskeyCredential).where(PasskeyCredential.user_id == user_id)
    )).scalars().all()

    if not creds:
        raise HTTPException(404, "No passkeys registered for this account")

    challenge = os.urandom(32)
    _store_challenge(f"auth:{user_id}", challenge)

    try:
        options = webauthn_generate_authentication_options(
            rp_id=RP_ID,
            challenge=challenge,
            allow_credentials=[
                PublicKeyCredentialDescriptor(
                    id=_bytes_to_b64url(c.credential_id)  # ✅ FIX
                )
                for c in creds
            ],
        )
        return _webauthn_to_dict(options)
    except Exception as e:
        debug_print(f"Failed to generate login options {str(e)}", tag="AUTH", color="red")
        raise HTTPException(500, "Failed to generate passkey authentication options")


async def verify_login_assertion(
    assertion: Dict[str, Any],
    request: Request,
    response: Response,
    main_session: AsyncSession,
    security_session: AsyncSession,
) -> None:
    try:
        raw_id = _b64decode(assertion["rawId"])
    except KeyError:
        raise HTTPException(400, "Invalid authenticator response")

    cred = await security_session.scalar(
        select(PasskeyCredential).where(PasskeyCredential.credential_id == raw_id)
    )
    if not cred:
        raise HTTPException(401, "Unknown passkey credential")

    challenge = _pop_challenge(f"auth:{cred.user_id}")
    if not challenge:
        raise HTTPException(400, "Authentication challenge expired")

    try:
        verification = verify_authentication_response(
            credential=assertion,
            expected_challenge=challenge,
            expected_rp_id=RP_ID,
            expected_origin=ORIGIN,
            credential_public_key=cred.public_key,
            credential_current_sign_count=cred.sign_count,
            require_user_verification=True,
        )
    except Exception:
        raise HTTPException(401, "Passkey verification failed")

    cred.sign_count = verification.new_sign_count
    cred.last_used_at = datetime.now(timezone.utc)
    await security_session.commit()

    user = await main_session.scalar(select(User).where(User.id == cred.user_id))
    if not user:
        raise HTTPException(404, "User not found")
    if user.is_banned:
        raise HTTPException(403, "Account disabled")

    device_secret = get_or_create_device_secret(request, response)
    device_hash = hash_device(device_secret)

    await register_or_update_device(
        user_id=user.id,
        device_hash=device_hash,
        user_agent=request.headers.get("user-agent", "unknown"),
        ip=request.client.host or "unknown",
        security_session=security_session,
    )

    token = create_access_token(user.id, device_hash=device_hash)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
    )

async def delete_passkeys(passkey_id: int, security_session: AsyncSession, user: User) -> None:
    res = await security_session.execute(
        delete(PasskeyCredential).where(
            PasskeyCredential.id == passkey_id,
            PasskeyCredential.user_id == user.id,
        )
    )
    return res
