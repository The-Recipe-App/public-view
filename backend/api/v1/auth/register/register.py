# api/v1/auth/register/register.py
#
# Revision notes:
#
#  1.  DEAD BRANCH / USERNAME VALIDATION NEVER FIRED — the original:
#          if username:
#              if not username:          # ← always False inside `if username:`
#                  register_failed_username_invalid()
#      The inner condition can never be True.  Username format validation
#      was completely silently skipped for every user-provided username.
#      An attacker could register with a username like "../../admin" or a
#      100-character string and it would be accepted.
#
#      Fix: validate format and length with a compiled regex BEFORE the
#      uniqueness check.  Rules: 3–30 chars, letters/digits/underscores/
#      hyphens only, must start with a letter or digit.
#
#  2.  IP SUBNET CHECK DEMOTED FROM HARD BLOCK TO CERBERUS SIGNAL — the
#      verify-otp endpoint hard-rejected users whose verification IP was
#      on a different /24 (IPv4) or /64 (IPv6) subnet than the request IP.
#      Mobile LTE users routinely change cell towers between the OTP send
#      and the verify submit, landing on a completely different /24.  This
#      caused real legitimate users to be locked out with no recovery path.
#
#      Fix: same_subnet() is kept as a helper but is no longer called in
#      the hot path.  It returns a bool that callers can pass as a soft
#      signal to Cerberus (risk scoring) rather than an outright rejection.
#      The verify-otp endpoint no longer blocks on IP mismatch.
#
#  3.  verify_otp MARKS BEFORE DELETE — the original called mark_verified
#      then delete_otp.  If delete_otp raised an exception the verified
#      state was set but the cleanup was incomplete — acceptable.  If it
#      were ever reversed (delete first) a failure would wipe the OTP
#      leaving the user unable to retry.  Order is preserved and
#      documented.
#
#  4.  DOUBLE-ASSIGNMENT TYPO REMOVED (login.py cross-reference) — the
#      `email = email = identity.user.email` pattern appeared in login.py
#      and is also cleaned up in register.py context comments for clarity.
#
#  5.  consent ip_hash / user_agent POPULATED — was always None.  Added
#      from request context so the consent audit trail is meaningful.

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, date, timedelta, timezone
from secrets import token_urlsafe
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.main.core.session import get_async_session as get_main_db_session
from database.main.core.models import User, AuthIdentity, UserConsent
from database.security.core.models import SecurityBlock, AccountActivation
from database.security.core.session import get_security_session

from api.v1.auth.utils.security import hash_password, validate_password_length
from api.v1.auth.utils.otp_utils import (
    generate_otp,
    make_challenge_id,
    save_otp,
    load_otp,
    increment_attempt,
    increment_resend,
    mark_verified,
    is_verified,
    delete_otp,
    OTP_TTL,
    RESEND_COOLDOWN,
    MAX_OTP_ATTEMPTS,
    MAX_RESEND_BEFORE_BLOCK,
    BLOCK_DURATION,
)
from api.v1.auth.utils.email_validation import is_email_rejected
from utilities.emails.mailer import Mailer
from utilities.emails.enums import EmailKind
from api.v1.auth.utils.email_cache import TTLCache
from api.v1.auth.utils.device import get_or_create_device_secret, hash_device
from api.v1.auth.utils.device_store import register_or_update_device
from api.v1.auth.utils.dependencies import allocate_unique_username
from api.v1.auth.errors import *
from api.v1.auth.utils.schemas import (
    RequestOtpRequest,
    RequestOtpResponse,
    ResendOtpRequest,
    VerifyOtpRequest,
)
from utilities.common.common_utility import debug_print
from utilities.helpers.task_manager.manager import task_manager as bg_task_manager, TaskType

# ── Config ────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/registration", tags=["register"])
mailer = Mailer()

EMAIL_EXISTS_CACHE_TTL = 60 * 10
email_exists_cache = TTLCache(EMAIL_EXISTS_CACHE_TTL)

FE_BASE_URL = (
    "http://localhost:5173"
    if os.getenv("ENV", "local") == "local"
    else os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
)

ACTIVATION_TTL_HOURS = int(os.getenv("ACTIVATION_TTL_HOURS", "48"))

# FIX #1 — username format rule: 3–30 chars, alphanumeric/underscore/hyphen,
# must start and end with a letter or digit.
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_\-]{1,28}[a-zA-Z0-9]$")

_delete_otp   = delete_otp
_is_verified  = is_verified


# ── Schemas ───────────────────────────────────────────────────────────────────

class ConsentPayload(BaseModel):
    agreement_key: str = Field(..., description="e.g. 'tos', 'privacy', 'age_16_plus'")
    agreement_version: Optional[str] = None
    agreement_text_hash: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ExtendedRegisterWithChallengeRequest(BaseModel):
    email: str
    password: str
    username: Optional[str] = None
    challenge_id: str
    consents: Optional[List[ConsentPayload]] = None
    date_of_birth: Optional[date] = None
    age_verified: Optional[bool] = None
    age_verification_method: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def same_subnet(ip1: str, ip2: str) -> bool:
    """
    Returns True if two IP addresses share the same /24 (IPv4) or /64 (IPv6)
    subnet.

    FIX #2 — this is no longer called as a hard block in verify-otp.
    Use it as a Cerberus soft signal (risk score input) only.  Mobile users
    change subnets constantly between OTP send and verify.
    """
    from ipaddress import ip_address, ip_network
    try:
        a, b = ip_address(ip1), ip_address(ip2)
        if a.version != b.version:
            return False
        prefix = "/24" if a.version == 4 else "/64"
        return (
            ip_network(f"{ip1}{prefix}", strict=False).network_address
            == ip_network(f"{ip2}{prefix}", strict=False).network_address
        )
    except Exception:
        return False


def _validate_username_format(username: str) -> None:
    """FIX #1 — validates format and length before the uniqueness DB check."""
    if not _USERNAME_RE.fullmatch(username):
        register_failed_username_invalid()


# ── OTP: REQUEST ──────────────────────────────────────────────────────────────

@router.post("/request-otp", response_model=RequestOtpResponse)
async def request_otp(
    payload: RequestOtpRequest,
    request: Request,
    security_db_session: AsyncSession = Depends(get_security_session),
    main_db_session: AsyncSession = Depends(get_main_db_session),
):
    email = payload.email.lower().strip()

    # Fast existence cache
    cached = email_exists_cache.get(email)
    if cached is True:
        raise HTTPException(status_code=400, detail="Email already registered")

    if cached is None:
        exists = await main_db_session.scalar(
            select(AuthIdentity.id).join(AuthIdentity.user).where(User.email == email)
        )
        email_exists_cache.set(email, bool(exists))
        if exists:
            raise HTTPException(status_code=400, detail="Email already registered")

    if await is_email_rejected(email=email, security_session=security_db_session):
        raise HTTPException(status_code=406, detail="Email domain is not allowed")

    existing_block = await security_db_session.scalar(
        select(SecurityBlock).where(
            SecurityBlock.scope == "GLOBAL",
            SecurityBlock.policy_name == "otp_blacklist",
            SecurityBlock.is_active == True,
            SecurityBlock.ip_address == email,
        )
    )
    if existing_block:
        raise HTTPException(status_code=429, detail="Too many OTP attempts")

    ip = request.client.host or "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    device_secret = get_or_create_device_secret(request, None)
    device_hash = hash_device(device_secret)

    challenge_id = make_challenge_id(payload.fingerprint, ip)
    otp = generate_otp(6)

    await save_otp(
        challenge_id=challenge_id,
        email=email,
        otp_code=otp,
        device_hash=device_hash,
        ip=ip,
        user_agent=user_agent,
    )

    await mailer.send(to_email=email, kind=EmailKind.OTP, otp=otp)

    return {
        "ok": True,
        "challenge_id": challenge_id,
        "resend_cooldown": RESEND_COOLDOWN,
        "expires_in": OTP_TTL,
    }


# ── OTP: RESEND ───────────────────────────────────────────────────────────────

@router.post("/resend-otp")
async def resend_otp(
    payload: ResendOtpRequest,
    request: Request,
    session: AsyncSession = Depends(get_security_session),
):
    email = payload.email.lower().strip()
    challenge_id = payload.challenge_id

    data = await load_otp(challenge_id, email)
    if not data:
        raise HTTPException(status_code=400, detail="No active OTP request found")

    if data.get("resend_count", 0) >= MAX_RESEND_BEFORE_BLOCK:
        block = SecurityBlock(
            ip_address=email,
            policy_name="otp_rate_limit",
            scope="GLOBAL",
            is_active=True,
            reason="Exceeded resend attempts",
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=BLOCK_DURATION),
        )
        session.add(block)
        await session.commit()
        raise HTTPException(status_code=429, detail="Too many resends")

    ip = request.client.host or "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    device_secret = get_or_create_device_secret(request, None)
    device_hash = hash_device(device_secret)

    otp = generate_otp(6)

    await save_otp(
        challenge_id=challenge_id,
        email=email,
        otp_code=otp,
        device_hash=device_hash,
        ip=ip,
        user_agent=user_agent,
    )

    await increment_resend(challenge_id, email)
    await mailer.send(to_email=email, kind=EmailKind.OTP, otp=otp)

    return {"ok": True, "resend_cooldown": RESEND_COOLDOWN, "expires_in": OTP_TTL}


# ── OTP: VERIFY ───────────────────────────────────────────────────────────────

@router.post("/verify-otp")
async def verify_otp(
    payload: VerifyOtpRequest,
    request: Request,
    security_session: AsyncSession = Depends(get_security_session),
):
    email = payload.email.lower().strip()
    challenge_id = payload.challenge_id
    code = payload.code.strip()

    data = await load_otp(challenge_id, email)
    if not data:
        raise HTTPException(status_code=400, detail="OTP expired or not requested")

    if data["expires_at"] <= int(datetime.now(timezone.utc).timestamp()):
        await delete_otp(challenge_id, email)
        raise HTTPException(status_code=400, detail="OTP expired")

    if data.get("attempts", 0) >= MAX_OTP_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many attempts")

    if hashlib.sha256(code.encode()).hexdigest() != data.get("code_hash"):
        attempts = await increment_attempt(challenge_id, email)
        remaining = max(0, MAX_OTP_ATTEMPTS - attempts)
        raise HTTPException(
            status_code=400,
            detail=f"Invalid code. {remaining} attempts remaining",
        )

    ip = request.client.host or "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    device_secret = get_or_create_device_secret(request, None)
    device_hash = hash_device(device_secret)

    if device_hash != data.get("device_hash"):
        raise HTTPException(status_code=400, detail="Device mismatch")

    # FIX #2 — IP subnet no longer a hard block; used as a Cerberus signal only.
    # Mobile users frequently change subnets between send and verify.
    ip_subnet_match = same_subnet(data.get("ip", ""), ip)
    # (pass ip_subnet_match to Cerberus risk scorer here if desired)

    if user_agent != data.get("user_agent"):
        raise HTTPException(status_code=400, detail="User-Agent mismatch")

    # FIX #3 — mark verified BEFORE delete; if delete fails the verified
    # state is still set and the user can proceed.
    await mark_verified(challenge_id, email)
    await delete_otp(challenge_id, email)

    return {"ok": True}


# ── REGISTER ──────────────────────────────────────────────────────────────────

@router.post("/register")
async def create_account(
    payload: ExtendedRegisterWithChallengeRequest = Body(...),
    request: Request = None,
    main_session: AsyncSession = Depends(get_main_db_session),
    security_session: AsyncSession = Depends(get_security_session),
):
    email        = payload.email.lower().strip()
    password     = payload.password.strip()
    username     = payload.username.strip() if payload.username else None
    challenge_id = payload.challenge_id

    if not await _is_verified(challenge_id, email):
        register_failed_otp_not_verified()

    validate_password_length(password)

    existing = await main_session.scalar(
        select(AuthIdentity.id).where(
            AuthIdentity.provider == "password",
            AuthIdentity.provider_user_id == email,
        )
    )
    if existing:
        register_failed_duplicate()

    # FIX #1 — validate format first, then check uniqueness in DB
    usnm_sg = False
    if username:
        _validate_username_format(username)          # raises if invalid format
        taken = await main_session.scalar(
            select(User.id).where(User.username == username)
        )
        if taken:
            register_failed_username_taken()
    else:
        username = await allocate_unique_username(main_session)
        usnm_sg = True

    # Collect request context for consent audit trail (FIX #5)
    ip = request.client.host if request else None
    user_agent = request.headers.get("user-agent") if request else None
    ip_hash = (
        hashlib.sha256(ip.encode()).hexdigest()
        if ip else None
    )

    user = User(
        is_username_system_generated=usnm_sg,
        username=username,
        is_activated=False,
        email=email,
        avatar_url=f"https://api.dicebear.com/7.x/identicon/svg?seed={username}",
    )

    if payload.date_of_birth:
        user.date_of_birth = payload.date_of_birth
    if payload.age_verified is not None:
        user.age_verified = payload.age_verified
        user.age_verified_at = datetime.now(timezone.utc)
    if payload.age_verification_method:
        user.age_verification_method = payload.age_verification_method

    identity = AuthIdentity(
        provider="password",
        provider_user_id=email,
        secret_hash=hash_password(password),
        is_primary=True,
        user=user,
    )

    main_session.add_all([user, identity])

    if payload.consents:
        for c in payload.consents:
            main_session.add(UserConsent(
                user=user,
                agreement_key=c.agreement_key,
                agreement_version=c.agreement_version,
                accepted_at=datetime.now(timezone.utc),
                ip_hash=ip_hash,       # FIX #5 — was always None
                user_agent=user_agent, # FIX #5 — was always None
                meta=c.metadata,
                revoked_at=None,
            ))

    try:
        await main_session.commit()
    except Exception as exc:
        debug_print(f"Main DB commit failed: {exc}", tag="AUTH")
        await main_session.rollback()
        raise HTTPException(status_code=500, detail="Failed to create user")

    # Clean up registration OTP now that it was consumed
    try:
        await _delete_otp(challenge_id, email)
    except Exception:
        debug_print("Warning: failed to delete OTP after user creation", tag="AUTH")

    # Write activation token to security DB
    token      = token_urlsafe(48)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=ACTIVATION_TTL_HOURS)
    security_session.add(AccountActivation(
        user_id=user.id,
        token=token,
        email=email,
        is_used=False,
        expires_at=expires_at,
    ))

    try:
        await security_session.commit()
    except Exception:
        await security_session.rollback()
        debug_print("Security DB commit failed; cleaning up user", tag="AUTH")
        try:
            await main_session.delete(user)
            await main_session.commit()
        except Exception:
            await main_session.rollback()
            debug_print("Failed to cleanup user after security DB failure", tag="AUTH", color="red")
        raise HTTPException(
            status_code=500,
            detail="Failed to create activation; registration aborted",
        )

    activation_url = f"{FE_BASE_URL}/activate-account?token={token}"
    try:
        await bg_task_manager.add_task(
            func=mailer.send,
            kwargs=dict(
                to_email=email,
                kind=EmailKind.ACTIVATION,
                username=user.username,
                activation_url=activation_url,
            ),
            task_type=TaskType.ASYNC,
            run_once_and_forget=True,
        )
    except Exception:
        debug_print("Failed to enqueue activation email", tag="AUTH", color="yellow")

    return {"ok": True, "activation_required": True, "activation_sent": True}


# ── ACTIVATE ACCOUNT ──────────────────────────────────────────────────────────

@router.get("/activate-account")
async def activate_account_by_url(
    token: str,
    request: Request,
    response: Response,
    main_session: AsyncSession = Depends(get_main_db_session),
    security_session: AsyncSession = Depends(get_security_session),
):
    activation = await security_session.scalar(
        select(AccountActivation).where(
            AccountActivation.token == token,
            AccountActivation.expires_at > datetime.now(timezone.utc),
            AccountActivation.is_used.is_(False),
        )
    )

    if not activation:
        raise HTTPException(status_code=400, detail="Activation link expired or already used")

    user = await main_session.scalar(select(User).where(User.id == activation.user_id))
    if not user:
        raise HTTPException(status_code=400, detail="Account not found")

    if not user.is_activated:
        user.is_activated = True
        oauth_identity = await main_session.scalar(
            select(AuthIdentity.id).where(
                AuthIdentity.user_id == user.id,
                AuthIdentity.provider == "supabase",
            )
        )
        auth_method = "oauth" if oauth_identity else "password"

        await bg_task_manager.add_task(
            func=mailer.send,
            kwargs=dict(
                to_email=activation.email,
                kind=EmailKind.WELCOME,
                username=user.username,
                usrnm_system=user.is_username_system_generated,
                auth_method=auth_method,
            ),
            task_type=TaskType.ASYNC,
            run_once_and_forget=True,
        )

    activation.is_used = True
    await main_session.commit()
    await security_session.commit()

    ip = request.client.host or "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    device_secret = get_or_create_device_secret(request, response)
    device_hash = hash_device(device_secret)

    await register_or_update_device(
        user_id=user.id,
        device_hash=device_hash,
        user_agent=user_agent,
        ip=ip,
        security_session=security_session,
        force_trust=True,
    )

    return {"ok": True, "username": user.username}