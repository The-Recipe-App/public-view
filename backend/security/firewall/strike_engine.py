# security/firewall/strike_engine.py

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from .strikes import register_strike
from .blacklist import add_block


def _build_identity_key(
    scope: str,
    ip: str,
    path: Optional[str] = None,
    fingerprint: Optional[str] = None,
) -> str:
    """
    Build a strike identity key based on escalation scope.
    """
    if scope == "ROUTE":
        return f"ROUTE:{path}:{ip}"

    if scope == "IP":
        return f"IP:{ip}"

    if scope == "IP_FINGERPRINT":
        fp = fingerprint or "no-fp"
        return f"IP_FP:{ip}:{fp}"

    if scope == "GLOBAL":
        return f"GLOBAL:{ip}"

    # Fallback: treat as IP
    return f"IP:{ip}"


async def escalate_if_needed(
    ip: str,
    policy_name: str,
    scope: str,
    window: float,
    threshold: int,
    path: Optional[str] = None,
    fingerprint: Optional[str] = None,
    promote_to_permanent: bool = False,
) -> Tuple[bool, Optional[str]]:
    """
    Policy-driven escalation handler.

    Returns:
        (promoted: bool, reason: Optional[str])
    """
    identity_key = _build_identity_key(
        scope=scope,
        ip=ip,
        path=path,
        fingerprint=fingerprint,
    )

    # Register a strike for this identity
    promoted = register_strike(
        identity_key=identity_key,
        window=window,
        threshold=threshold,
    )

    if not promoted:
        return False, None

    # Escalation triggered — decide block type
    now = datetime.now(timezone.utc)
    reason = f'Policy "{policy_name}" triggered escalation at scope "{scope}".'

    if promote_to_permanent or scope == "GLOBAL":
        # Permanent block
        await add_block(
            ip=ip,
            policy_name=policy_name,
            scope=scope,
            reason=reason,
            fingerprint_hash=fingerprint,
            route=path,
            is_permanent=True,
            expires_at=None,
        )
        return True, f'Permanent block applied by policy "{policy_name}".'

    # Temporary block (window-based)
    expires_at = now + timedelta(seconds=window)

    await add_block(
        ip=ip,
        policy_name=policy_name,
        scope=scope,
        reason=reason,
        fingerprint_hash=fingerprint,
        route=path,
        is_permanent=False,
        expires_at=expires_at,
    )

    return True, f'Temporary block applied by policy "{policy_name}" until "{expires_at.isoformat()}".'
