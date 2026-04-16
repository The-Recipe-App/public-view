from fastapi import APIRouter
from api.v1.auth.register.register import router as register_router
from api.v1.auth.login.login import router as login_router
from api.v1.auth.passkey.passkey import router as passkey_router
from api.v1.auth.password.change_password import router as change_password_router
from api.v1.auth.oauth.oauth import router as oauth_router

# ─────────────────────────────
# Constants & Prebindings
# ─────────────────────────────

auth_router = APIRouter(prefix="/auth", tags=["auth"])

auth_router.include_router(register_router)
auth_router.include_router(login_router)
auth_router.include_router(passkey_router)
auth_router.include_router(change_password_router)
auth_router.include_router(oauth_router)