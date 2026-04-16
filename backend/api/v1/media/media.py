import os
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, bindparam

from database.main.core.session import get_async_session
from database.main.core.models import User

from api.v1.media.media_stream import avatar_response, recipe_media_response
from utilities.common.common_utility import debug_print


media_router = APIRouter(prefix="/media", tags=["media"])


# ============================================================
# Precompiled User Avatar Lookup
# ============================================================

UID = bindparam("uid")

AVATAR_KEY_LOOKUP = (
    select(User.avatar_key)
    .where(User.id == UID)
    .limit(1)
)


# ============================================================
# Avatar Endpoint (Fastest Possible)
# ============================================================

@media_router.get("/avatars/{user_id}")
async def get_avatar(
    user_id: int,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    debug_print(f"[media] avatar request user_id={user_id}", tag="MEDIA")

    avatar_key = await session.scalar(
        AVATAR_KEY_LOOKUP,
        {"uid": user_id},
    )

    if not avatar_key:
        raise HTTPException(404, "No avatar set")

    bucket = os.getenv("S3_BUCKET_NAME")
    if not bucket:
        raise HTTPException(500, "Missing S3_BUCKET_NAME")

    return await avatar_response(
        request=request,
        bucket=bucket,
        key=avatar_key,
    )

# ============================================================
# Recipe Media Endpoint
# ============================================================

@media_router.get("/recipes/{media_key:path}")
async def get_recipe_media(
    request: Request, 
    media_key: str,
):
    """
    Streams recipe images/videos securely.
    Frontend uses:

        /media/recipes/<storage_key>
    """

    debug_print(f"[media] recipe request key={media_key}", tag="MEDIA")

    return await recipe_media_response(
        request=request, 
        key=media_key,
    )
