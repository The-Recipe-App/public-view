from datetime import datetime, timezone
import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database.main.core.session import get_async_session
from database.security.core.session import get_security_session
from database.main.core.models import Policy, PolicyVersion, UserConsent, User
from database.security.core.models import PendingUserConsent
from api.v1.auth.utils.dependencies import get_current_user

from api.legal.schemas import (
    ActivePoliciesResponse,
    PolicyHistoryResponse,
    PreRegisterConsentPayload,
    PreRegisterConsentResponse,
    UserConsentPayload,
    UserConsentResponse,
    MyConsentsResponse,
)

router = APIRouter(prefix="/legal", tags=["legal"])


# ─────────────────────────────
# Helpers
# ─────────────────────────────

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ─────────────────────────────
# Active policies (registration modal)
# ─────────────────────────────

@router.get("/active", response_model=ActivePoliciesResponse)
async def get_active_policies(
    locale: str = "en",
    session: AsyncSession = Depends(get_async_session),
):
    """
    Returns all currently active policies.

    ✅ Content is NOT stored in DB anymore.
    Instead DB provides static file URL + hash.
    """

    stmt = (
        select(Policy, PolicyVersion)
        .join(PolicyVersion, PolicyVersion.policy_id == Policy.id)
        .where(
            PolicyVersion.is_active.is_(True),
            PolicyVersion.locale == locale,
        )
        .order_by(Policy.key.asc())
    )

    res = await session.execute(stmt)

    items = []
    for policy, version in res.all():
        items.append(
            {
                "key": policy.key,
                "title": policy.title,
                "description": policy.description,
                "version": version.version,
                "effective_at": version.effective_at,

                # ✅ Static file reference
                "file_url": version.file_url,
                "file_format": version.file_format,

                # Legal proof hash
                "text_hash": version.text_hash,
            }
        )

    return {"ok": True, "policies": items}


# ─────────────────────────────
# Policy history
# ─────────────────────────────

@router.get("/{policy_key}/versions", response_model=PolicyHistoryResponse)
async def get_policy_versions(
    policy_key: str,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Returns version history for one policy.

    No markdown/html returned — only metadata + file_url.
    """

    policy = await session.scalar(select(Policy).where(Policy.key == policy_key))
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    res = await session.execute(
        select(PolicyVersion)
        .where(PolicyVersion.policy_id == policy.id)
        .order_by(PolicyVersion.effective_at.desc())
    )

    return {
        "ok": True,
        "versions": [
            {
                "version": v.version,
                "effective_at": v.effective_at,
                "is_active": v.is_active,

                # ✅ Static reference
                "file_url": v.file_url,
                "file_format": v.file_format,

                "text_hash": v.text_hash,
            }
            for v in res.scalars()
        ],
    }


# ─────────────────────────────
# Pre-registration consent (OTP-bound)
# ─────────────────────────────

@router.post("/consent/pre-register", response_model=PreRegisterConsentResponse)
async def accept_policies_preregister(
    request: Request,
    payload: PreRegisterConsentPayload,
    session: AsyncSession = Depends(get_security_session),
):
    """
    Records consent BEFORE registration is completed.

    Stored in security DB as PendingUserConsent.

    Payload includes:
    - agreement_key
    - version
    - text_hash
    """

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    # Idempotent: clear old consents for same challenge
    await session.execute(
        delete(PendingUserConsent).where(
            PendingUserConsent.challenge_id == payload.challenge_id
        )
    )

    rows = []
    for a in payload.agreements:
        rows.append(
            PendingUserConsent(
                challenge_id=payload.challenge_id,
                agreement_key=a.key,
                agreement_version=a.version,
                agreement_text_hash=a.text_hash,
                accepted_at=datetime.now(timezone.utc),
                ip_hash=sha256(ip) if ip else None,
                user_agent=ua,
                meta=payload.meta.model_dump(),
            )
        )

    session.add_all(rows)
    await session.commit()

    return {"ok": True, "accepted": len(rows)}


# ─────────────────────────────
# Post-login consent (re-accept, upgrades)
# ─────────────────────────────

@router.post("/consent", response_model=UserConsentResponse)
async def accept_policies_authenticated(
    request: Request,
    payload: UserConsentPayload,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Records consent AFTER login (policy upgrades, new agreements).
    Append-only ledger.
    """

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    rows = []
    for a in payload.agreements:
        rows.append(
            UserConsent(
                user_id=user.id,
                agreement_key=a.key,
                agreement_version=a.version,
                agreement_text_hash=a.text_hash,
                accepted_at=datetime.now(timezone.utc),
                ip_hash=sha256(ip) if ip else None,
                user_agent=ua,
                meta=payload.meta.model_dump(),
            )
        )

    session.add_all(rows)
    await session.commit()

    return {"ok": True, "accepted": len(rows)}


# ─────────────────────────────
# User consent ledger
# ─────────────────────────────

@router.get("/me/consents", response_model=MyConsentsResponse)
async def my_consents(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Returns the user's active consent ledger.
    """

    res = await session.execute(
        select(UserConsent)
        .where(
            UserConsent.user_id == user.id,
            UserConsent.revoked_at.is_(None),
        )
        .order_by(UserConsent.accepted_at.desc())
    )

    return {
        "ok": True,
        "consents": [
            {
                "agreement_key": c.agreement_key,
                "agreement_version": c.agreement_version,
                "accepted_at": c.accepted_at,
                "text_hash": c.agreement_text_hash,
                "meta": c.meta,
            }
            for c in res.scalars()
        ],
    }
