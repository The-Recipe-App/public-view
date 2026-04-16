from fastapi import APIRouter
from api.v1.auth.auth import auth_router
from api.v1.health.health import health_router
from api.v1.profile.profile import profile_router
from api.v1.media.media import media_router
from api.v1.profile.username_stream import router as username_stream_router
from api.v1.profile.username_check import router as username_check_router
from api.v1.auth.passkey.passkey import router as passkey_router
from api.v1.recipes import router as recipes_router
from api.v1.notifications.notifications import router as notifications_router
from api.v1.follows.follows import router as follows_router

v1_router = APIRouter(prefix="/v1")

v1_router.include_router(auth_router)
v1_router.include_router(health_router)
v1_router.include_router(profile_router)
v1_router.include_router(media_router)
v1_router.include_router(username_stream_router)
v1_router.include_router(username_check_router)
v1_router.include_router(passkey_router)
v1_router.include_router(recipes_router)
v1_router.include_router(notifications_router)
v1_router.include_router(follows_router)
# Search Router is moved to lifespan. This is due to the blocking import of SentenceTransformer.