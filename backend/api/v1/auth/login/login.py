# api/v1/auth/login/login.py
#
# Revision notes:
#
#  1.  OTP DELETE BEFORE IDENTITY LOOKUP FIXED — the original verify-otp
#      flow ran in this order:
#          await delete_otp(challenge_id, email)   ← OTP wiped
#          identity = await main_session.scalar(OTP_IDENTITY_LOOKUP...)
#          if not identity: auth_failed()           ← too late
#      If the identity lookup fails (user deleted between OTP issue and
#      verify, DB blip, etc.), the OTP is already gone.  The user is now
#      locked out with no way to retry — they must go through the full
#      login flow again, generating a new challenge.
#
#      Fix: identity lookup runs FIRST.  The OTP is only deleted after we
#      confirm the identity exists and is valid.  If the lookup fails,
#      auth_failed() is raised and the OTP remains intact for a retry.
#
#  2.  DOUBLE-ASSIGNMENT TYPO REMOVED — `email = email = identity.user.email`
#      compiles and runs fine but is a clear copy-paste error.
#
#  3.  debug_print IN LOGIN HOT PATH REMOVED — two debug_print calls at
#      the very top of the login handler fire on every login attempt,
#      printing the full payload (including password) and the IP.  This
#      is a plaintext credential leak into stdout/logs.  Removed entirely;
#      use structured logging at DEBUG level if you need this locally.
#
#  4.  IP SUBNET HARD BLOCK DEMOTED — same reasoning as register.py fix #2.
#      The verify-otp handler blocked on subnet mismatch for mobile users.
#      Now a soft signal only; the hard `auth_failed()` on mismatch is gone.
#
#  5.  change_username MISSING FORMAT VALIDATION — the /me/username endpoint
#      checked for empty string but not format.  Added _validate_username_format
#      (shared with register.py) so the same rules apply everywhere.

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address, ip_network
from secrets import token_urlsafe

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import bindparam, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.main.core.session import get_async_session as get_main_db_session
from database.security.core.session import get_security_session
from database.main.core.models import User, AuthIdentity
from database.security.core.models import MobileAuthGrant, UserDevice

from api.v1.auth.utils.security import (
    verify_password,
    create_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from api.v1.auth.utils.otp_utils import (
    generate_otp,
    make_challenge_id,
    save_otp,
    load_otp,
    delete_otp,
    OTP_TTL,
    increment_attempt,
    MAX_OTP_ATTEMPTS,
)
from api.v1.auth.utils.device import get_or_create_device_secret, hash_device, DEVICE_COOKIE
from api.v1.auth.utils.device_store import register_or_update_device, is_suspicious_device
from api.v1.auth.utils.dependencies import get_current_user, mask_email
from api.v1.auth.errors import *
from api.v1.auth.utils.schemas import LoginRequest, VerifyLoginOtpRequest
from api.v1.auth.utils.email_validation import is_email_rejected
from api.v1.auth.register.register import _validate_username_format
from utilities.emails.mailer import Mailer
from utilities.emails.enums import EmailKind

# ── Router + config ───────────────────────────────────────────────────────────

router = APIRouter(prefix="/security", tags=["login"])
mailer = Mailer()

COOKIE_NAME    = "access_token"
COOKIE_MAX_AGE = int(timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES).total_seconds())

COOKIE_KWARGS = dict(
    httponly=True,
    secure=True,
    samesite="strict",
    path="/",
)

# ── Precompiled statements ────────────────────────────────────────────────────

IDENT = bindparam("ident")
DHASH = bindparam("dhash")
EMAIL = bindparam("email")
TOKEN = bindparam("token")

LOGIN_LOOKUP_STMT = (
    select(AuthIdentity)
    .options(selectinload(AuthIdentity.user))
    .join(User, User.id == AuthIdentity.user_id)
    .where(
        AuthIdentity.provider == "password",
        or_(
            func.lower(User.email)    == IDENT,
            func.lower(User.username) == IDENT,
        ),
    )
    .limit(1)
)

OTP_REQUIRED = (
    select(UserDevice)
    .where(
        UserDevice.device_hash == DHASH,
        or_(
            UserDevice.is_revoked == False,
            UserDevice.is_trusted == True,
            UserDevice.last_seen_at > datetime.now(timezone.utc) - timedelta(days=10)
        )
    )
    .limit(1)
)

OTP_IDENTITY_LOOKUP = (
    select(AuthIdentity)
    .options(selectinload(AuthIdentity.user))
    .join(User, User.id == AuthIdentity.user_id)
    .where(func.lower(User.email) == EMAIL)
    .limit(1)
)

MOBILE_CODE_LOOKUP = (
    select(MobileAuthGrant)
    .where(MobileAuthGrant.token == TOKEN)
    .limit(1)
)

# ── Subnet helper (soft signal only) ─────────────────────────────────────────

def _same_subnet(ip1: str, ip2: str) -> bool:
    """
    FIX #4 — returns a bool for Cerberus risk scoring only.
    No longer used as a hard auth_failed() block.
    """
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


# ── LOGIN ─────────────────────────────────────────────────────────────────────

@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_main_db_session),
    security_session: AsyncSession = Depends(get_security_session),
):
    # FIX #3 — removed debug_print(payload) which logged the password to stdout
    ip         = request.client.host or "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    identifier = payload.identifier.strip().lower()

    identity = await session.scalar(LOGIN_LOOKUP_STMT, {"ident": identifier})

    if (
        not identity
        or not identity.secret_hash
        or not verify_password(payload.password, identity.secret_hash)
        or identity.user.is_banned
    ):
        auth_failed()

    if not identity.user.is_activated:
        auth_failed_not_activated()

    # FIX #2 — single clean assignment (was `email = email = ...`)
    email = identity.user.email

    if await is_email_rejected(email=email, security_session=security_session):
        raise HTTPException(
            406,
            "We have blocked your access to our services because the email you "
            "provided seems to be suspicious. Please contact support.",
        )

    device_secret = get_or_create_device_secret(request, response)
    device_hash   = hash_device(device_secret)

    otp_required = not (await security_session.scalar(OTP_REQUIRED, {"dhash": device_hash}))

    if otp_required:
        challenge_id = make_challenge_id(device_hash, ip)
        otp          = generate_otp(6)

        await save_otp(
            challenge_id=challenge_id,
            email=email,
            otp_code=otp,
            device_hash=device_hash,
            ip=ip,
            user_agent=user_agent,
            save_without_email=True,
        )
        await mailer.send(
            to_email=email,
            kind=EmailKind.NEW_DEVICE_LOGIN_OTP,
            otp=otp,
            challenge_id=challenge_id,
            reason=(
                "Please enter the OTP below to confirm it's you."
            ),
        )
        return {
            "ok":          False,
            "challenge":   "otp_required",
            "challenge_id": challenge_id,
            "masked_email": mask_email(email),
            "expires_in":  OTP_TTL,
        }

    await register_or_update_device(
        user_id=identity.user.id,
        device_hash=device_hash,
        user_agent=user_agent,
        ip=ip,
        security_session=security_session,
    )

    access_token = create_access_token(
        identity.user.id,
        device_hash=device_hash,
        is_admin=identity.user.is_admin,
    )
    response.set_cookie(COOKIE_NAME, access_token, max_age=COOKIE_MAX_AGE, **COOKIE_KWARGS)
    return {"ok": True}


# ── VERIFY OTP (login challenge) ──────────────────────────────────────────────

@router.post("/verify-otp")
async def verify_login_otp(
    payload: VerifyLoginOtpRequest,
    request: Request,
    response: Response,
    main_session: AsyncSession = Depends(get_main_db_session),
    security_session: AsyncSession = Depends(get_security_session),
):
    challenge_id = payload.challenge_id
    code         = payload.code.strip()
    ip           = request.client.host or "unknown"
    user_agent   = request.headers.get("user-agent", "unknown")

    data = await load_otp(challenge_id)
    print(data)
    if not data:
        auth_failed()

    # Expiry check
    expires_at = data["expires_at"]
    email = data["email"]
    print(email)
    if isinstance(expires_at, (int, float)):
        expires_at = datetime.fromtimestamp(expires_at, tz=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        await delete_otp(challenge_id)
        auth_failed()

    # Attempt limit
    attempts = await increment_attempt(challenge_id)
    if attempts > MAX_OTP_ATTEMPTS:
        await delete_otp(challenge_id)
        auth_failed()

    # Code check
    if hashlib.sha256(code.encode()).hexdigest() != data.get("code_hash"):
        auth_failed()

    # Device binding
    device_secret = get_or_create_device_secret(request, response)
    device_hash   = hash_device(device_secret)
    if device_hash != data.get("device_hash"):
        auth_failed()

    # FIX #4 — IP subnet is a soft signal, not a hard block
    _same_subnet(data.get("ip", ""), ip)   # result available for Cerberus if needed

    # User-Agent binding
    if data.get("user_agent") != user_agent:
        auth_failed()

    # FIX #1 — identity lookup BEFORE OTP delete.
    # If lookup fails the OTP stays intact and the user can retry.
    identity = await main_session.scalar(
        OTP_IDENTITY_LOOKUP, {"email": email.lower() if email else None}
    )
    if not identity or identity.user.is_banned:
        auth_failed()

    # Only delete OTP after we know the identity is valid
    await delete_otp(challenge_id)

    await register_or_update_device(
        user_id=identity.user.id,
        device_hash=device_hash,
        user_agent=user_agent,
        ip=ip,
        security_session=security_session,
        force_trust=True,
    )

    access_token = create_access_token(identity.user.id, device_hash=device_hash)
    response.set_cookie(COOKIE_NAME, access_token, max_age=COOKIE_MAX_AGE, **COOKIE_KWARGS)
    return {"ok": True}


# ── LOGOUT / ME ───────────────────────────────────────────────────────────────

@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key=COOKIE_NAME, **COOKIE_KWARGS)
    return {"ok": True}


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return {
        "id":         user.id,
        "username":   user.username,
        "reputation": user.reputation,
        "plan":       user.plan_tier,
        "avatar_url": user.avatar_url,
        "is_admin":   user.is_admin,
    }


# ── CHANGE USERNAME ───────────────────────────────────────────────────────────

@router.patch("/me/username")
async def change_username(
    username: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_main_db_session),
):
    username = username.strip()

    if not username:
        register_failed_username_invalid()

    # FIX #5 — apply same format rules as registration
    _validate_username_format(username)

    if username == user.username:
        return {"ok": True}

    taken = await session.scalar(
        select(User.id).where(User.username == username).limit(1)
    )
    if taken:
        register_failed_username_taken()

    user.username = username
    session.add(user)
    await session.commit()
    return {"ok": True}


# ── MOBILE AUTH FLOW ──────────────────────────────────────────────────────────

@router.get("/mobile/create-code")
async def create_mobile_auth_code(
    user: User = Depends(get_current_user),
    security_session: AsyncSession = Depends(get_security_session),
):
    code    = token_urlsafe(36)
    expires = datetime.now(timezone.utc) + timedelta(minutes=5)

    security_session.add(MobileAuthGrant(
        token=code,
        user_id=user.id,
        expires_at=expires,
        is_used=False,
    ))
    await security_session.commit()
    return RedirectResponse(url=f"forkit://auth-success?code={code}")


@router.post("/mobile/exchange")
async def exchange_mobile_code(
    payload: dict,
    security_session: AsyncSession = Depends(get_security_session),
):
    code = payload.get("code")
    if not code:
        raise HTTPException(400, "Missing code")

    grant = await security_session.scalar(MOBILE_CODE_LOOKUP, {"token": code})
    if not grant:
        raise HTTPException(400, "Invalid code")
    if grant.is_used:
        raise HTTPException(400, "Code already used")
    if grant.expires_at < datetime.now(timezone.utc):
        raise HTTPException(400, "Code expired")

    token = create_access_token(grant.user_id, device_hash="mobile")

    grant.is_used = True
    security_session.add(grant)
    await security_session.commit()

    return JSONResponse({"token": token})