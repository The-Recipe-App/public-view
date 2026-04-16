from datetime import datetime, timezone
from email.utils import parseaddr
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from database.security.core.models import EmailDomainPolicy


async def is_email_rejected(
    *,
    email: str,
    security_session: AsyncSession,
    fail_closed_on_error: bool = False,  # optional: if True, return True when internal errors happen
) -> bool:
    """
    Single authoritative email decision function.

    Returns:
        True  -> reject email
        False -> allow email
    """

    try:
        if not email or not isinstance(email, str):
            return True  # malformed, fail closed

        # Extract a bare address from inputs like: "No Reply <no.reply@domain.com>"
        _name, addr = parseaddr(email)
        addr = (addr or "").strip()

        if "@" not in addr:
            return True  # malformed, fail closed

        # Use rsplit to get last '@' part (safer)
        domain = addr.rsplit("@", 1)[1].lower().strip()

        # Remove trailing dot if present (some inputs have "example.com.")
        if domain.endswith("."):
            domain = domain[:-1]

        # Normalize some common presentation variants (optional)
        # e.g. strip surrounding brackets, etc. Already handled by parseaddr above.

        # Query DB case-insensitively. We normalize comparison to lower(domain).
        now_utc = datetime.now(timezone.utc)
        stmt = (
            select(EmailDomainPolicy)
            .where(
                func.lower(EmailDomainPolicy.domain) == domain,
                or_(
                    EmailDomainPolicy.expires_at.is_(None),
                    EmailDomainPolicy.expires_at > now_utc,
                ),
            )
            .limit(1)
        )

        policy = await security_session.scalar(stmt)

        # Unknown domain → allow
        if not policy:
            return False

        # Explicit allow overrides everything
        if getattr(policy, "is_allowed", False):
            return False

        # Blocked or disposable → reject
        if getattr(policy, "is_blocked", False) or getattr(policy, "is_disposable", False):
            return True

        # Default: allow
        return False

    except Exception as e:
        # keep your previous behavior (log + allow) unless fail_closed_on_error requested
        # replace print with your app logger where appropriate
        print("is_email_rejected error:", e)
        if fail_closed_on_error:
            return True
        return False
