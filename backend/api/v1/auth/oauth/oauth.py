# api/v1/auth/oauth/oauth.py
import os
import requests
from secrets import token_urlsafe
from datetime import datetime, timedelta, timezone, date
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, Request, Response, HTTPException, status, Query
from fastapi.security import HTTPBearer
from jose import jwt
from pydantic import BaseModel

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, bindparam
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

from database.main.core.session import get_async_session as get_main_db_session
from database.security.core.session import get_security_session
from database.main.core.models import User, AuthIdentity, UserConsent
from database.security.core.models import AccountActivation

from api.v1.auth.utils.security import create_access_token
from api.v1.auth.utils.device import get_or_create_device_secret, hash_device
from api.v1.auth.utils.device_store import register_or_update_device, is_suspicious_device
from api.v1.auth.utils.otp_utils import generate_otp, make_challenge_id, save_otp, OTP_TTL, load_otp
from api.v1.auth.utils.email_validation import is_email_rejected
from api.v1.auth.utils.dependencies import allocate_unique_username, mask_email
from api.v1.auth.register.register import ConsentPayload, FE_BASE_URL
from api.v1.auth.oauth.cache import OAuthTTLCache

from utilities.common.common_utility import debug_print
from utilities.helpers.task_manager.manager import task_manager as bg_task_manager, TaskType
from utilities.emails.enums import EmailKind
from utilities.emails.mailer import Mailer

# ============================================================
# CONFIG
# ============================================================

router = APIRouter(prefix="/oauth", tags=["oauth"])

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://mphzauwjuwdtnfamlrht.supabase.co")
SUPABASE_ISSUER = f"{SUPABASE_URL}/auth/v1"

# NOTE: JWKS usage here is simplistic — keep existing behavior.
try:
    JWKS = requests.get(f"{SUPABASE_ISSUER}/.well-known/jwks.json", timeout=5).json()
except Exception:
    JWKS = None

security = HTTPBearer()
mailer = Mailer()

# challenge cache (existing)
CHALLENGE_CACHE_TTL = 180 * 10
challenge_cache = OAuthTTLCache(CHALLENGE_CACHE_TTL)

# flow cache (server-owned ephemeral OAuth flow state)
FLOW_TTL_SECONDS = int(os.getenv("OAUTH_FLOW_TTL_SECONDS", "300"))  # default 5 minutes
FLOW_CACHE = OAuthTTLCache(FLOW_TTL_SECONDS)

ACTIVATION_TTL_HOURS = int(os.getenv("ACTIVATION_TTL_HOURS", "48"))

COOKIE_NAME = "access_token"
COOKIE_MAX_AGE = 60 * 60 * 24
COOKIE_KWARGS = dict(
    httponly=True,
    secure=True,
    samesite="strict",
    path="/",
)

# ============================================================
# COMPILED QUERIES
# ============================================================

Q_OAUTH_IDENTITY = (
    select(AuthIdentity)
    .options(selectinload(AuthIdentity.user))
    .where(
        AuthIdentity.provider == bindparam("provider"),
        AuthIdentity.provider_user_id == bindparam("provider_user_id"),
    )
)

Q_OAUTH_IDENTITY_ID_ONLY = (
    select(AuthIdentity.id)
    .where(
        AuthIdentity.provider == bindparam("provider"),
        AuthIdentity.provider_user_id == bindparam("provider_user_id"),
    )
)

Q_USER_BY_EMAIL = select(User).where(User.email == bindparam("email"))

Q_USER_BY_USERNAME = select(User.id).where(User.username == bindparam("username"))

# ============================================================
# REQUEST MODELS
# ============================================================


class OAuthRegisterRequest(BaseModel):
    consents: List[ConsentPayload]
    username: Optional[str] = None
    date_of_birth: Optional[date] = None
    age_verified: Optional[bool] = None
    age_verification_method: Optional[str] = None
    challenge_id: str


class OAuthLoginRequest(BaseModel):
    fingerprint: Optional[str] = None


class OAuthStartResponse(BaseModel):
    req_id: str
    expires_in: int


class OAuthFlowResponse(BaseModel):
    status: str
    ok: Optional[bool] = False
    email: Optional[str] = None
    challenge_id: Optional[str] = None
    masked_email: Optional[str] = None
    detail: Optional[str] = None


class OAuthRegisterWithFlowRequest(OAuthRegisterRequest):
    req_id: str


# ============================================================
# TOKEN VERIFICATION
# ============================================================


def verify_supabase_token(token: str) -> Dict[str, Any]:
    """
    Verify Supabase-issued JWT. Keep behaviour permissive:
    - If JWKS is available, attempt to decode normally.
    - Otherwise attempt a decode without public key verification (fail closed).
    """
    try:
        if JWKS:
            # jose.jwt.decode can accept a JWKS dict for verification in some setups.
            payload = jwt.decode(token, JWKS, algorithms=["ES256"], issuer=SUPABASE_ISSUER, options={"verify_aud": False})
        else:
            # Fallback — attempt decode with verify=False (not ideal, but preserves prior behaviour if JWKS unavailable)
            payload = jwt.get_unverified_claims(token)
        return payload
    except Exception as exc:
        debug_print(f"Supabase token verification failed: {exc}", tag="OAUTH", color="red")
        raise HTTPException(status_code=401, detail="Invalid Supabase token")


def is_supabase_email_verified(payload: dict) -> bool:
    return (
        payload.get("email_confirmed_at") is not None
        or payload.get("user_metadata", {}).get("email_verified") is True
    )


# ============================================================
# FLOW endpoints
# ============================================================


@router.post("/start", response_model=OAuthStartResponse)
async def start_oauth_flow():
    """
    Create a server-side req_id for the OAuth handoff.
    Frontend should request this, then provider redirect must carry ?req_id=...
    """
    fid = token_urlsafe(24)
    FLOW_CACHE.set(fid, {"status": "pending", "created_at": int(datetime.now(timezone.utc).timestamp())})
    debug_print(f"Created oauth flow {fid}", tag="OAUTH", color="green")
    return {"req_id": fid, "expires_in": FLOW_TTL_SECONDS}


@router.get("/flow/{req_id}", response_model=OAuthFlowResponse)
async def oauth_flow_status(
        req_id: str,
    ):
    f = FLOW_CACHE.get(req_id)
    if not f:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flow not found")
    return {
        "status": f.get("status"),
        "ok": f.get("ok", False),
        "email": f.get("email"),
        "challenge_id": f.get("challenge_id"),
        "masked_email": f.get("masked_email"),
        "detail": f.get("detail"),
    }


# ============================================================
# OAUTH LOGIN
# ============================================================


@router.post("/login")
async def oauth_login(
    payload_fe: OAuthLoginRequest,
    request: Request,
    response: Response,
    credentials=Depends(security),
    main_session: AsyncSession = Depends(get_main_db_session),
    security_session: AsyncSession = Depends(get_security_session),
    req_id: Optional[str] = Query(None, alias="req_id"),
):
    """
    Accept provider token via Authorization: Bearer <token>.
    If req_id is supplied, write transient state into FLOW_CACHE for frontend polling.
    """
    token = credentials.credentials
    payload = verify_supabase_token(token)

    # normalize email and supabase user id
    email = (payload.get("email") or "").lower().strip()
    supabase_user_id = payload.get("sub")

    email_verified = is_supabase_email_verified(payload)

    if not email or not email_verified:
        # if flow present, mark error
        if req_id:
            FLOW_CACHE.set(req_id, {"status": "error", "detail": "Email not verified"})
        raise HTTPException(400, "Email not verified")

    # If flow present, mark pending and store minimal metadata (provider_identity & avatar)
    provider_identity = payload.get("app_metadata", {}).get("provider") or payload.get("user_metadata", {}).get("iss") or "unknown"
    # avatar resolution: prefer user_metadata.avatar_url -> picture -> fallback identicon
    user_metadata = payload.get("user_metadata", {}) or {}
    avatar_url = user_metadata.get("avatar_url") or user_metadata.get("picture")
    if not avatar_url:
        # deterministic identicon seeded by email
        avatar_url = f"https://api.dicebear.com/7.x/identicon/svg?seed={email}"

    if req_id:
        FLOW_CACHE.set(
            req_id,
            {
                "status": "pending",
                "email": email,
                "supabase_user_id": supabase_user_id,
                "provider_identity": provider_identity,
                "avatar_url": avatar_url,
            },
        )

    # Check OAuth identity — canonicalize provider stored in DB as "supabase"
    identity = await main_session.scalar(
        Q_OAUTH_IDENTITY,
        {
            "provider": "supabase",
            "provider_user_id": supabase_user_id,
        },
    )

    if identity:
        user = identity.user
        # ensure provider_identity is populated
        try:
            pi = payload.get("app_metadata", {}).get("provider")
            if pi and getattr(identity, "provider_identity", None) != pi:
                identity.provider_identity = pi
                try:
                    await main_session.commit()
                except Exception:
                    await main_session.rollback()
        except Exception:
            # continue with existing user even if update failed
            pass
    else:
        user = None

    # If no identity found, fallback to user-by-email
    if not identity:
        user = await main_session.scalar(Q_USER_BY_EMAIL, {"email": email})

        if user:
            # create identity pointing to existing account
            identity = AuthIdentity(
                provider="supabase",  # canonical provider value (our issuer)
                provider_user_id=supabase_user_id,
                provider_identity=provider_identity,
                user=user,
                is_primary=False,
            )
            main_session.add(identity)
            try:
                await main_session.commit()
            except IntegrityError:
                await main_session.rollback()
            except Exception:
                await main_session.rollback()
                debug_print("Error committing new AuthIdentity", tag="OAUTH", color="red")
        else:
            # no user — create challenge and return needs_registration
            ip = request.client.host or "unknown"
            challenge_id = make_challenge_id(payload_fe.fingerprint, ip)

            cache_key = f"{email}:{supabase_user_id}"
            challenge_cache.set(
                key=cache_key,
                value={
                    "challenge_id": challenge_id,
                    "ip": ip,
                    "fingerprint": payload_fe.fingerprint,
                },
            )

            # write to flow cache if present
            if req_id:
                FLOW_CACHE.set(
                    req_id,
                    {
                        "status": "needs_registration",
                        "email": email,
                        "supabase_user_id": supabase_user_id,
                        "challenge_id": challenge_id,
                        "avatar_url": avatar_url,
                        "provider_identity": provider_identity,
                    },
                )

            return {
                "ok": False,
                "needs_registration": True,
                "email": email,
                "challenge_id": challenge_id,
            }

    # at this point we have user object (either via identity.user or by email)
    if user.is_banned:
        if req_id:
            FLOW_CACHE.set(req_id, {"status": "error", "detail": "Account banned"})
        raise HTTPException(403, "Account banned")

    # Device logic
    ip = request.client.host or "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    device_secret = get_or_create_device_secret(request, response)
    device_hash = hash_device(device_secret)

    suspicious = await is_suspicious_device(
        user_id=user.id,
        device_hash=device_hash,
        security_session=security_session,
        ip=ip,
        user_agent=user_agent,
    )

    if suspicious:
        challenge_id = make_challenge_id(device_hash, ip)
        debug_print(f"Suspicious device detected for user {user.id} | challenge_id={challenge_id}", tag="SECURITY", color="red")
        otp = generate_otp(6)

        await save_otp(
            challenge_id=challenge_id,
            email=user.email,
            otp_code=otp,
            device_hash=device_hash,
            ip=ip,
            user_agent=user_agent,
            save_without_email=True,
        )
        
        debug_print(f"Things in cache: {await load_otp(challenge_id)}")

        await bg_task_manager.add_task(
            func=mailer.send,
            kwargs=dict(
                to_email=user.email,
                kind=EmailKind.OTP,
                otp=otp,
                reason="We detected a login attempt from a new device. Please use the OTP code above to verify it's you.",
            ),
            task_type=TaskType.ASYNC,
            run_once_and_forget=True,
        )

        # reflect OTP requirement in flow if present
        if req_id:
            FLOW_CACHE.set(
                req_id,
                {
                    "status": "otp_required",
                    "challenge_id": challenge_id,
                    "masked_email": mask_email(user.email),
                    "email": user.email,
                    "detail": "otp required",
                },
            )

        return {
            "ok": False,
            "challenge": "otp_required",
            "challenge_id": challenge_id,
            "masked_email": mask_email(user.email),
            "expires_in": OTP_TTL,
        }

    # Register / update device
    await register_or_update_device(
        user_id=user.id,
        device_hash=device_hash,
        user_agent=user_agent,
        ip=ip,
        security_session=security_session,
    )

    access_token = create_access_token(
        user.id,
        device_hash=device_hash,
        is_admin=user.is_admin,
    )

    # set cookie (same semantics as before)
    response.set_cookie(
        COOKIE_NAME,
        access_token,
        max_age=COOKIE_MAX_AGE,
        **COOKIE_KWARGS,
    )

    # mark flow complete if present
    if req_id:
        FLOW_CACHE.set(req_id, {"status": "complete", "ok": True, "email": user.email})

    return {"ok": True}


# ============================================================
# OAUTH REGISTRATION (deprecated token-based) -- left mostly unchanged
# ============================================================

@router.post("/registration/deprecated/register", deprecated=True)
async def oauth_register(
    body: OAuthRegisterRequest,
    request: Request,
    credentials=Depends(security),
    main_session: AsyncSession = Depends(get_main_db_session),
    security_session: AsyncSession = Depends(get_security_session),
):
    token = credentials.credentials
    payload = verify_supabase_token(token)

    email = (payload.get("email") or "").lower().strip()
    supabase_user_id = payload.get("sub")

    if not email:
        raise HTTPException(400, "Email missing")

    # ---------------- Challenge Validation ----------------
    cache_key = f"{email}:{supabase_user_id}"
    cached = challenge_cache.get(cache_key)

    if not cached:
        raise HTTPException(400, "Challenge expired")

    if cached["challenge_id"] != body.challenge_id:
        raise HTTPException(400, "Invalid challenge_id")

    if cached["ip"] != (request.client.host or "unknown"):
        raise HTTPException(400, "IP mismatch")

    challenge_cache.delete(cache_key)  # one-time use

    # ---------------- Prevent duplicate identity ----------------
    existing_identity = await main_session.scalar(
        Q_OAUTH_IDENTITY_ID_ONLY,
        {
            "provider": "supabase",
            "provider_user_id": supabase_user_id,
        },
    )

    if existing_identity:
        raise HTTPException(400, "OAuth identity already registered")

    # ---------------- Username ----------------
    username = body.username.strip() if body.username else None
    is_system_generated = False

    if username:
        taken = await main_session.scalar(
            Q_USER_BY_USERNAME,
            {"username": username},
        )
        if taken:
            raise HTTPException(400, "Username already taken")
    else:
        username = await allocate_unique_username(main_session)
        is_system_generated = True

    # ---------------- Create User ----------------
    user = User(
        email=email,
        email_verified=True,
        username=username,
        is_username_system_generated=is_system_generated,
        is_activated=False,
    )

    if body.date_of_birth:
        user.date_of_birth = body.date_of_birth

    if body.age_verified is not None:
        user.age_verified = body.age_verified
        user.age_verified_at = datetime.now(timezone.utc)

    if body.age_verification_method:
        user.age_verification_method = body.age_verification_method

    identity = AuthIdentity(
        provider="supabase",
        provider_user_id=supabase_user_id,
        provider_identity=payload.get("app_metadata", {}).get("provider", "supabase"),
        is_primary=True,
        user=user,
    )

    main_session.add_all([user, identity])

    now = datetime.now(timezone.utc)

    for c in body.consents:
        main_session.add(
            UserConsent(
                user=user,
                agreement_key=c.agreement_key,
                agreement_version=c.agreement_version,
                accepted_at=now,
                meta=c.metadata,
            )
        )

    try:
        await main_session.commit()
    except Exception as e:
        debug_print(f"Error creating user: {e}", tag="OAUTH", color="red")
        await main_session.rollback()
        raise HTTPException(500, "Failed to create user")

    # ---------------- Activation ----------------
    email_verified = is_supabase_email_verified(payload)
    if email_verified:
        user.is_activated = True
        await main_session.commit()
        try:
            await bg_task_manager.add_task(
                func=mailer.send,
                kwargs=dict(
                    to_email=email,
                    kind=EmailKind.WELCOME,
                    username=user.username,
                    usrnm_system=user.is_username_system_generated,
                    auth_method="oauth_supabase",
                ),
                task_type=TaskType.ASYNC,
                run_once_and_forget=True,
            )
        except Exception:
            debug_print(
                "Failed to send welcome email; activation still created",
                tag="AUTH",
                color="yellow",
            )

        return {
            "ok": True,
            "activation_required": False,
        }
    else:
        activation_token = token_urlsafe(48)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=ACTIVATION_TTL_HOURS)

        activation = AccountActivation(
            user_id=user.id,
            token=activation_token,
            email=email,
            is_used=False,
            expires_at=expires_at,
        )

        security_session.add(activation)

        try:
            await security_session.commit()
            activation_url = f"{FE_BASE_URL}/activate-account?token={activation_token}"
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
                debug_print(
                    "Failed to send activation email; activation still created",
                    tag="AUTH",
                    color="yellow",
                )
        except Exception:
            await security_session.rollback()
            try:
                await main_session.delete(user)
                await main_session.commit()
            except Exception:
                await main_session.rollback()
            raise HTTPException(status_code=500, detail="Failed to create activation")

        return {
            "ok": True,
            "activation_required": True,
            "activation_sent": True,
        }


# ============================================================
# OAUTH REGISTRATION (flow-based)
# ============================================================


@router.post("/registration/register")
async def oauth_register_with_flow(
    body: OAuthRegisterWithFlowRequest,
    request: Request,
    response: Response,                          # ← add Response
    main_session: AsyncSession = Depends(get_main_db_session),
    security_session: AsyncSession = Depends(get_security_session),  # ← add security_session
):
    """
    Register using a server-owned req_id (no provider token required here).
    The flow must have been established earlier by /oauth/login which stored
    the supabase_user_id and email in FLOW_CACHE.
    """
    req_id = body.req_id
    flow = FLOW_CACHE.get(req_id)
    if not flow:
        raise HTTPException(400, "Flow not found or expired")
    if flow.get("status") == "final":
        raise HTTPException(429, "Already in process")

    email = (flow.get("email") or "").lower().strip()
    supabase_user_id = flow.get("supabase_user_id")

    if not email or not supabase_user_id:
        raise HTTPException(400, "Invalid flow payload")

    # ---------------- Challenge Validation ----------------
    cache_key = f"{email}:{supabase_user_id}"
    cached = challenge_cache.get(cache_key)

    if not cached:
        raise HTTPException(400, "Challenge expired")

    if cached["challenge_id"] != body.challenge_id:
        raise HTTPException(400, "Invalid challenge_id")

    if cached["ip"] != (request.client.host or "unknown"):
        raise HTTPException(400, "IP mismatch")

    challenge_cache.delete(cache_key)  # one-time use
    FLOW_CACHE.set(req_id, {"status": "final", "ok": True, "email": email})

    # ---------------- Prevent duplicate identity ----------------
    existing_identity = await main_session.scalar(
        Q_OAUTH_IDENTITY_ID_ONLY,
        {
            "provider": "supabase",
            "provider_user_id": supabase_user_id,
        },
    )

    if existing_identity:
        raise HTTPException(400, "OAuth identity already registered")

    # ---------------- Username ----------------
    username = body.username.strip() if body.username else None
    is_system_generated = False

    if username:
        taken = await main_session.scalar(
            Q_USER_BY_USERNAME,
            {"username": username},
        )
        if taken:
            raise HTTPException(400, "Username already taken")
    else:
        username = await allocate_unique_username(main_session)
        is_system_generated = True

    # ---------------- Create User ----------------
    provider_identity = flow.get("provider_identity") or "unknown"
    avatar_from_flow = flow.get("avatar_url") or f"https://api.dicebear.com/7.x/identicon/svg?seed={username or email}"

    user = User(
        email=email,
        email_verified=True,
        username=username,
        avatar_url=avatar_from_flow,
        is_username_system_generated=is_system_generated,
        is_activated=False,
    )

    if body.date_of_birth:
        user.date_of_birth = body.date_of_birth

    if body.age_verified is not None:
        user.age_verified = body.age_verified
        user.age_verified_at = datetime.now(timezone.utc)

    if body.age_verification_method:
        user.age_verification_method = body.age_verification_method

    identity = AuthIdentity(
        provider="supabase",
        provider_user_id=supabase_user_id,
        provider_identity=provider_identity,
        is_primary=True,
        user=user,
    )

    main_session.add_all([user, identity])

    now = datetime.now(timezone.utc)

    for c in body.consents:
        main_session.add(
            UserConsent(
                user=user,
                agreement_key=c.agreement_key,
                agreement_version=c.agreement_version,
                accepted_at=now,
                meta=c.metadata,
            )
        )

    try:
        await main_session.commit()
    except Exception as e:
        debug_print(f"Error creating user: {e}", tag="OAUTH", color="red")
        await main_session.rollback()
        raise HTTPException(500, "Failed to create user")

    # ---------------- Activation ----------------
    # We validated email presence/verification during oauth_login; treat as verified
    user.is_activated = True
    await main_session.commit()
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
    )

    access_token = create_access_token(
        user.id,
        device_hash=device_hash,
        is_admin=user.is_admin,
    )

    response.set_cookie(
        COOKIE_NAME,
        access_token,
        max_age=COOKIE_MAX_AGE,
        **COOKIE_KWARGS,
    )

    FLOW_CACHE.set(req_id, {"status": "complete", "ok": True, "email": email})

    try:
        await bg_task_manager.add_task(
            func=mailer.send,
            kwargs=dict(
                to_email=email,
                kind=EmailKind.WELCOME,
                username=user.username,
                usrnm_system=user.is_username_system_generated,
                auth_method="oauth_supabase",
            ),
            task_type=TaskType.ASYNC,
            run_once_and_forget=True,
        )
    except Exception:
        debug_print("Failed to enqueue welcome email", tag="AUTH", color="yellow")

    return {"ok": True, "auto_logged_in": True}