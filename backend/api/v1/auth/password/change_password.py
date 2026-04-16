# password_change.py
from datetime import datetime, timedelta, timezone
import hashlib
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, Request, Response, HTTPException, Body
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.main.core.session import get_async_session as get_main_db_session
from database.main.core.models import AuthIdentity, User
from database.security.core.models import SecurityBlock, UserDevice
from database.security.core.session import get_security_session

from api.v1.auth.utils.security import hash_password, validate_password_length
from api.v1.auth.utils.dependencies import _cache_remove_user, get_current_user, revoke_all_other_devices
from api.v1.auth.utils.device import hash_device, get_or_create_device_secret, DEVICE_COOKIE
from api.v1.auth.utils.otp_utils import (
    generate_otp,
    make_challenge_id,
    save_otp,
    load_otp,
    increment_attempt,
    increment_resend,
    mark_verified,
    delete_otp,
    OTP_TTL,
    RESEND_COOLDOWN,
    MAX_OTP_ATTEMPTS,
    MAX_RESEND_BEFORE_BLOCK,
    BLOCK_DURATION,
)

from utilities.emails.mailer import Mailer
from utilities.emails.enums import EmailKind
from utilities.common.common_utility import debug_print

from utilities.helpers.task_manager.manager import task_manager as bg_task_manager, TaskType

router = APIRouter(prefix="/password-change", tags=["auth.password_change"])

mailer = Mailer()

# -----------------------
# Pydantic models
# -----------------------
class RequestChangeOtpRequest(BaseModel):
    fingerprint: Optional[str] = None


class ResendChangeOtpRequest(BaseModel):
    challenge_id: str


class VerifyOtpRequest(BaseModel):
    challenge_id: str
    code: str


class ConfirmChangeRequest(BaseModel):
    challenge_id: str
    code: str
    new_password: str


# -----------------------
# Helpers / small services (module-local)
# -----------------------
def _make_user_scoped_challenge_id(user_id: str, fingerprint: Optional[str], ip: str) -> str:
    fp = f"user:{user_id}|fingerprint:{(fingerprint or '')}"
    return make_challenge_id(fp, ip)



async def _require_email_for_user(session: AsyncSession, user_id: int) -> str:
    user = await session.get(User, user_id)
    if not user or not user.email:
        raise HTTPException(status_code=400, detail="Account email not found")

    return user.email.lower().strip()


async def _validate_otp_or_raise(challenge_id: str, email: str, code: str):
    debug_print(f"validating otp for {email}")
    data = await load_otp(challenge_id)
    if not data:
        raise HTTPException(status_code=400, detail="OTP expired or not requested")

    attempts = int(data.get("attempts", 0))
    if attempts >= MAX_OTP_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many attempts; temporarily blocked")

    if hashlib.sha256(code.encode()).hexdigest() != data.get("code_hash"):
        attempts = await increment_attempt(challenge_id)
        remaining = max(0, MAX_OTP_ATTEMPTS - attempts)
        raise HTTPException(
            status_code=400,
            detail=f"Invalid code. {remaining} attempts remaining",
        )

    # mark verified here (caller can still delete if they want)
    await mark_verified(challenge_id, email)


# -----------------------
# Routes
# -----------------------
@router.post("/request-otp")
async def request_change_otp(
    response: Response,
    payload: RequestChangeOtpRequest = Body(...),
    request: Request = None,
    main_session: AsyncSession = Depends(get_main_db_session),
    security_session: AsyncSession = Depends(get_security_session),
    current_user=Depends(get_current_user),
):
    """
    Send OTP to the user's email. Respects global OTP blacklist on the account email.
    """
    email = await _require_email_for_user(main_session, current_user.id)

    # check global OTP blacklist (per-email)
    existing_block = await security_session.scalar(
        select(SecurityBlock).where(
            SecurityBlock.scope == "GLOBAL",
            SecurityBlock.policy_name == "otp_blacklist",
            SecurityBlock.is_active.is_(True),
            SecurityBlock.ip_address == email,
        )
    )
    if existing_block:
        raise HTTPException(status_code=429, detail="Too many OTP attempts for this account")

    ip = request.client.host if request and request.client else "unknown"
    challenge_id = _make_user_scoped_challenge_id(str(current_user.id), payload.fingerprint, ip)

    otp = generate_otp(6)
    device_secret = get_or_create_device_secret(request, response)
    device_hash = hash_device(device_secret)
    user_agent = request.headers.get("user-agent", "unknown")

    # atomic-ish single save call to OTP store
    await save_otp(challenge_id, otp, device_hash, ip, user_agent)

    # send email async via background task (fire-and-forget)
    try:
        await bg_task_manager.add_task(
            func=mailer.send,
            kwargs={"to_email": email, "kind": EmailKind.PASSWORD_CHANGE_OTP, "otp": otp},
            task_type=TaskType.ASYNC,
            run_once_and_forget=True,
        )
    except Exception as e:
        debug_print(f"Failed to schedule OTP email: {e}", tag="AUTH", color="yellow")

    return {
        "ok": True,
        "challenge_id": challenge_id,
        "resend_cooldown": RESEND_COOLDOWN,
        "expires_in": OTP_TTL,
    }


@router.post("/resend-otp")
async def resend_change_otp(
    response: Response,
    payload: ResendChangeOtpRequest = Body(...),
    request: Request = None,
    main_session: AsyncSession = Depends(get_main_db_session),
    security_session: AsyncSession = Depends(get_security_session),
    current_user=Depends(get_current_user),
):
    """
    Resend an active OTP; if too many resends, create a route-scoped block.
    """
    challenge_id = payload.challenge_id
    email = await _require_email_for_user(main_session, current_user.id)

    data = await load_otp(challenge_id, email)
    if not data:
        raise HTTPException(status_code=400, detail="No active OTP request found")

    resends = int(data.get("resend_count", 0))
    if resends >= MAX_RESEND_BEFORE_BLOCK:
        block = SecurityBlock(
            ip_address=email,
            route="/auth/password-change/request-otp",
            policy_name="otp_rate_limit",
            scope="ROUTE",
            is_permanent=False,
            is_active=True,
            reason="Exceeded resend attempts",
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=BLOCK_DURATION),
        )
        security_session.add(block)
        await security_session.commit()
        raise HTTPException(status_code=429, detail="Too many resends; temporarily blocked")

    otp = generate_otp(6)
    device_secret = get_or_create_device_secret(request, response)
    device_hash = hash_device(device_secret)
    ip = request.client.host or "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    await save_otp(challenge_id, email, otp, device_hash, ip, user_agent)
    await increment_resend(challenge_id, email)

    try:
        await bg_task_manager.add_task(
            func=mailer.send,
            kwargs={"to_email": email, "kind": EmailKind.PASSWORD_CHANGE_OTP, "otp": otp},
            task_type=TaskType.ASYNC,
            run_once_and_forget=True,
        )
    except Exception as e:
        debug_print(f"Failed to schedule resend OTP email: {e}", tag="AUTH", color="yellow")

    return {
        "ok": True,
        "resend_cooldown": RESEND_COOLDOWN,
        "expires_in": OTP_TTL,
    }


@router.post("/verify-otp")
async def verify_change_otp(
    payload: VerifyOtpRequest = Body(...),
    main_session: AsyncSession = Depends(get_main_db_session),
    current_user=Depends(get_current_user),
):
    """
    Verify OTP only (no password change).
    """
    challenge_id = payload.challenge_id
    code = payload.code.strip()

    email = await _require_email_for_user(main_session, current_user.id)
    await _validate_otp_or_raise(challenge_id, email, code)
    # mark verified but don't delete; keep for confirm endpoint to pick up if needed
    await mark_verified(challenge_id, email)
    return {"ok": True}


@router.post("/confirm")
async def confirm_change_password(
    payload: ConfirmChangeRequest = Body(...),
    request: Request = None,
    main_session: AsyncSession = Depends(get_main_db_session),
    current_user=Depends(get_current_user),
):
    """
    Finalize password change after OTP verification.
    - Validates OTP
    - Updates or creates password identity
    - Commits main DB in one transaction
    - Fire-and-forget: revoke other devices, send notification email, clear caches
    """

    challenge_id = payload.challenge_id
    code = payload.code.strip()
    new_password = payload.new_password or ""

    if not new_password:
        raise HTTPException(status_code=400, detail="New password is required")

    # determine email to which OTP was sent (and later email notifications)
    email = await _require_email_for_user(main_session, current_user.id)

    # validate OTP (raises if invalid)
    await _validate_otp_or_raise(challenge_id, email, code)

    # consume OTP now (so it cannot be reused)
    await delete_otp(challenge_id)

    # validate password locally
    validate_password_length(new_password)

    # load specifically the password identity (do not rely on any identity)
    password_identity = await main_session.scalar(
        select(AuthIdentity).where(
            AuthIdentity.user_id == current_user.id,
            AuthIdentity.provider == "password",
        )
    )

    # update or create password identity
    try:
        if not password_identity:
            main_session.add(
                AuthIdentity(
                    provider_identity="system",
                    user_id=current_user.id,
                    provider="password",
                    provider_user_id=str(current_user.id),
                    secret_hash=hash_password(new_password),
                    is_primary=False,
                )
            )
        else:
            password_identity.secret_hash = hash_password(new_password)

        await main_session.commit()
    except Exception as e:
        debug_print(f"Failed to update password: {e}", tag="AUTH", color="red")
        await main_session.rollback()
        raise HTTPException(status_code=500, detail="Failed to update password")

    # Post-change side-effects (fire-and-forget)
    try:
        device_secret = None
        if request:
            device_secret = request.cookies.get(DEVICE_COOKIE)

        # schedule revoke of other devices in background (do NOT duplicate DB updates here)
        try:
            await bg_task_manager.add_task(
                func=revoke_all_other_devices,
                kwargs={
                    "user_id": current_user.id,
                    "current_device_secret": device_secret or "",
                },
                task_type=TaskType.ASYNC,
                run_once_and_forget=True,
            )
        except Exception as e:
            debug_print(f"Failed to schedule device revocation: {e}", tag="AUTH", color="yellow")

        # clear caches
        try:
            _cache_remove_user(current_user.id)
        except Exception as e:
            debug_print(f"Failed to clear user cache: {e}", tag="AUTH", color="yellow")

        # schedule password-changed email
        try:
            await bg_task_manager.add_task(
                func=mailer.send,
                kwargs={"to_email": email, "kind": EmailKind.PASSWORD_CHANGED},
                task_type=TaskType.ASYNC,
                run_once_and_forget=True,
            )
        except Exception as e:
            debug_print(f"Failed to schedule password-changed email: {e}", tag="AUTH", color="yellow")

    except Exception as e:
        debug_print(f"Post password-change error: {e}", tag="AUTH", color="yellow")

    return {"ok": True}
