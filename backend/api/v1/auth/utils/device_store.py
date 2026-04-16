# api/v1/auth/utils/device_store.py
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Tuple, Callable
import time
import ipaddress

from sqlalchemy import select, func, and_, bindparam
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from database.security.core.models import UserDevice, SecurityBlock

# ------------------------------
# Configuration
# ------------------------------
TRUSTED_AUTO_LIMIT = 5
TRUST_SCORE_TO_TRUST = 2

RISK_THRESHOLD = 4
NEW_DEVICE_WINDOW = timedelta(hours=1)
DEVICE_VELOCITY_WINDOW = timedelta(hours=24)
DEVICE_VELOCITY_THRESHOLD = 3
TRUST_DECAY = timedelta(days=90)

# IP-reputation tuning
IP_MULTIUSER_THRESHOLD = 5      # > X distinct users from same IP => suspicious

# Small in-memory TTL caches
_DEVICE_CACHE: Dict[Tuple[int, str], Tuple[float, bool]] = {}
_CACHE_TTL_SECONDS = 15
_CACHE_MAX_SIZE = 10_000

_ASN_CACHE: Dict[str, Tuple[float, Optional[int]]] = {}
_ASN_CACHE_TTL = 3600  # 1 hour

# Optional pluggable ASN resolver:
# set_asn_resolver(fn) where fn(ip_str) -> Optional[int]
_asn_resolver: Optional[Callable[[str], Optional[int]]] = None


def set_asn_resolver(fn: Callable[[str], Optional[int]]):
    global _asn_resolver
    _asn_resolver = fn


# ------------------------------
# Precompiled SQL statements
# ------------------------------
GET_DEVICE_STMT = (
    select(UserDevice)
    .where(
        UserDevice.user_id == bindparam("user_id"),
        UserDevice.device_hash == bindparam("device_hash"),
    )
)

COUNT_TRUSTED_STMT = (
    select(func.count())
    .select_from(UserDevice)
    .where(
        and_(
            UserDevice.user_id == bindparam("user_id"),
            UserDevice.is_trusted.is_(True),
            UserDevice.is_revoked.is_(False),
        )
    )
)

COUNT_RECENT_DEVICES_STMT = (
    select(func.count())
    .select_from(UserDevice)
    .where(
        and_(
            UserDevice.user_id == bindparam("user_id"),
            UserDevice.first_seen_at >= bindparam("window_start"),
        )
    )
)

CHECK_IP_BLOCK_STMT = (
    select(SecurityBlock.id)
    .where(
        and_(
            SecurityBlock.ip_address == bindparam("ip"),
            SecurityBlock.is_active.is_(True),
        )
    )
    .limit(1)
)

COUNT_USERS_BY_IP_STMT = (
    select(func.count(func.distinct(UserDevice.user_id)))
    .where(
        UserDevice.last_ip == bindparam("ip")
    )
)

# ------------------------------
# Utilities
# ------------------------------
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _cache_get(user_id: int, device_hash: str, ip: Optional[str]) -> Optional[bool]:
    key = (user_id, device_hash, ip)
    entry = _DEVICE_CACHE.get(key)
    if not entry:
        return None
    ts, value = entry
    if time.time() - ts > _CACHE_TTL_SECONDS:
        _DEVICE_CACHE.pop(key, None)
        return None
    return value

def _cache_set(user_id: int, device_hash: str, value: bool, ip: Optional[str] = None):
    if len(_DEVICE_CACHE) > _CACHE_MAX_SIZE:
        _DEVICE_CACHE.clear()
    _DEVICE_CACHE[(user_id, device_hash, ip)] = (time.time(), value)


def _asn_lookup(ip: str) -> Optional[int]:
    """Fast cached ASN lookup using the pluggable resolver if present."""
    if not _asn_resolver:
        return None
    entry = _ASN_CACHE.get(ip)
    if entry:
        ts, asn = entry
        if time.time() - ts < _ASN_CACHE_TTL:
            return asn
    try:
        asn = _asn_resolver(ip)
    except Exception:
        asn = None
    _ASN_CACHE[ip] = (time.time(), asn)
    return asn


def _ip_to_subnet(ip: str) -> Optional[str]:
    """Return a coarse subnet string for IP (v4 /24, v6 /64)."""
    try:
        parsed = ipaddress.ip_address(ip)
        if parsed.version == 4:
            network = ipaddress.ip_network(f"{ip}/24", strict=False)
            return f"{network.network_address}/24"
        else:
            network = ipaddress.ip_network(f"{ip}/64", strict=False)
            return f"{network.network_address}/64"
    except Exception:
        return None


# ------------------------------
# Risk engine (fast + paranoid heuristics)
# ------------------------------
async def calculate_device_risk(
    user_id: int,
    device_hash: str,
    security_session: AsyncSession,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> int:
    """
    Paranoid but performant risk engine.
    ip and user_agent are optional but strongly recommended.
    """

    now = _now()
    risk = 0

    # 0) IP block check (hard stop, very cheap)
    if ip:
        blocked = await security_session.scalar(
            CHECK_IP_BLOCK_STMT, {"ip": ip}
        )
        if blocked:
            return 10

    # 1) fetch device
    device: Optional[UserDevice] = await security_session.scalar(
        GET_DEVICE_STMT, {"user_id": user_id, "device_hash": device_hash}
    )

    # ---------------- existing device ----------------
    if device:
        # revoked => immediate high-risk
        if device.is_revoked:
            return 10

        # Subnet mismatch (e.g. /24 changed) => suspicious
        if ip and getattr(device, "last_ip", None):
            prev_subnet = getattr(device, "last_ip_subnet", None)
            cur_subnet = _ip_to_subnet(ip)
            if prev_subnet and cur_subnet and prev_subnet != cur_subnet:
                risk += 3

        # ASN change if resolver present
        if ip and getattr(device, "last_asn", None) is not None and _asn_resolver:
            cur_asn = _asn_lookup(ip)
            if cur_asn is not None and device.last_asn != cur_asn:
                risk += 4

        # Dormancy
        if device.last_seen_at:
            inactive = now - device.last_seen_at
            if inactive > TRUST_DECAY:
                device.trust_score = max(0, device.trust_score - 1)
                device.is_trusted = device.trust_score >= TRUST_SCORE_TO_TRUST
            elif inactive > timedelta(days=30):
                risk += 2

        # New device age penalty
        if device.first_seen_at and (now - device.first_seen_at) < NEW_DEVICE_WINDOW:
            risk += 2

        # trust baseline adjustment
        if device.is_trusted:
            risk -= 2
        else:
            risk += 1

        # low trust_score penalty
        if device.trust_score < TRUST_SCORE_TO_TRUST:
            risk += 1

        # device saturation
        trusted_count = await security_session.scalar(
            COUNT_TRUSTED_STMT, {"user_id": user_id}
        )
        if trusted_count and trusted_count >= TRUSTED_AUTO_LIMIT:
            risk += 2

        # IP reputation: many distinct users on same IP (proxy farm)
        if ip:
            users_on_ip = await security_session.scalar(
                COUNT_USERS_BY_IP_STMT, {"ip": ip}
            )
            if users_on_ip and users_on_ip >= IP_MULTIUSER_THRESHOLD:
                risk += 3

        # small floor
        if risk < 0:
            risk = 0

        return risk

    # ---------------- new device (not present) ----------------
    trusted_count = await security_session.scalar(
        COUNT_TRUSTED_STMT, {"user_id": user_id}
    )
    if trusted_count and trusted_count >= TRUSTED_AUTO_LIMIT:
        risk += 2

    window_start = now - DEVICE_VELOCITY_WINDOW
    recent_count = await security_session.scalar(
        COUNT_RECENT_DEVICES_STMT, {"user_id": user_id, "window_start": window_start}
    )
    if recent_count and recent_count >= DEVICE_VELOCITY_THRESHOLD:
        risk += 3

    # IP reputation for brand-new devices
    if ip:
        users_on_ip = await security_session.scalar(
            COUNT_USERS_BY_IP_STMT, {"ip": ip}
        )
        if users_on_ip and users_on_ip >= IP_MULTIUSER_THRESHOLD:
            risk += 3

    risk += 2  # base risk for unknown device
    return risk


# ------------------------------
# Public boolean (cached)
# ------------------------------
async def is_suspicious_device(
    user_id: int,
    device_hash: str,
    security_session: AsyncSession,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> bool:
    """
    Cached boolean wrapper; strongly prefer passing ip and user_agent.
    """

    # Cache key should include ip if provided — a device might be ok from one IP but
    # suspicious from a bad IP; include ip in cache only when given.
    cache_key_hash = device_hash
    cached = _cache_get(user_id, device_hash, ip)
    if cached is not None:
        return cached

    risk = await calculate_device_risk(
        user_id=user_id,
        device_hash=device_hash,
        security_session=security_session,
        ip=ip,
        user_agent=user_agent,
    )

    result = risk >= RISK_THRESHOLD
    _cache_set(user_id, device_hash, result, ip)
    return result


# ------------------------------
# register or update device (records IP / ASN / subnet)
# ------------------------------
async def register_or_update_device(
    user_id: int,
    device_hash: str,
    user_agent: str,
    ip: str,
    security_session: AsyncSession,
    force_trust: bool = False,
):
    now = _now()

    device: Optional[UserDevice] = await security_session.scalar(
        GET_DEVICE_STMT, {"user_id": user_id, "device_hash": device_hash}
    )

    # compute subnet & asn (fast, in-process)
    subnet = _ip_to_subnet(ip)
    asn = _asn_lookup(ip)

    if device:
        if device.is_revoked:
            return device

        device.last_ip = ip
        device.user_agent = user_agent
        device.last_seen_at = now

        # persist subnet & asn if we computed them
        if subnet:
            device.last_ip_subnet = subnet
        if asn is not None:
            device.last_asn = asn

        device.trust_score = (device.trust_score or 0) + 1
        if device.trust_score >= TRUST_SCORE_TO_TRUST:
            device.is_trusted = True

        await security_session.commit()
        _cache_set(user_id=user_id, device_hash=device_hash, value=False)
        return device

    # new device path
    try:
        trusted_count = await security_session.scalar(
            COUNT_TRUSTED_STMT, {"user_id": user_id}
        )
        auto_trust = trusted_count is None or trusted_count < TRUSTED_AUTO_LIMIT

        device = UserDevice(
            user_id=user_id,
            device_hash=device_hash,
            user_agent=user_agent,
            first_ip=ip,
            last_ip=ip,
            first_seen_at=now,
            last_seen_at=now,
            is_trusted=bool(auto_trust or force_trust),
            trust_score=1 if (auto_trust or force_trust) else 0,
            is_revoked=False,
            last_ip_subnet=subnet,
            last_asn=asn,
            meta={},
        )

        security_session.add(device)
        await security_session.commit()
        _cache_set(user_id=user_id, device_hash=device_hash, value=False)
        return device

    except IntegrityError:
        await security_session.rollback()
        device = await security_session.scalar(
            GET_DEVICE_STMT, {"user_id": user_id, "device_hash": device_hash}
        )
        if not device:
            raise RuntimeError("Device upsert race failed")

        device.last_ip = ip
        device.last_seen_at = now
        if subnet:
            device.last_ip_subnet = subnet
        if asn is not None:
            device.last_asn = asn

        device.trust_score = (device.trust_score or 0) + 1
        if device.trust_score >= TRUST_SCORE_TO_TRUST:
            device.is_trusted = True

        await security_session.commit()
        _cache_set(user_id=user_id, device_hash=device_hash, value=False)
        return device
