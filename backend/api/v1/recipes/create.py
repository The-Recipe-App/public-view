# api/v1/recipes/create.py
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form,
    Request,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select

from database.main.core.session import get_async_session
from database.main.core.models import (
    User,
    Recipe,
    Ingredient,
    RecipeStep,
    License,
    RecipeLicense,
    RecipeLineageSnapshot,
    Activity,
    RecipeMedia,
    MediaType,
)

from api.v1.auth.utils.dependencies import get_current_user
from api.v1.recipes.schemas import CreateRecipeReq, ForkRecipeReq

from api.v1.media.storage import s3
from utilities.common.common_utility import debug_print

import io
import os
import uuid
import json
from typing import Optional, List

router = APIRouter()

MAX_STEPS = 200
MAX_INGREDIENTS = 200

# Upload limits (fallback if you want env overrides)
DEFAULT_MAX_IMAGE_MB = int(os.getenv("MAX_IMAGE_MB", "20"))
DEFAULT_MAX_VIDEO_MB = int(os.getenv("MAX_VIDEO_MB", "200"))


# ----------------------------
# License Validation
# ----------------------------
async def _ensure_license(session: AsyncSession, license_id: Optional[int]):
    if license_id is None:
        return None

    lic = await session.get(License, license_id)
    if not lic:
        raise HTTPException(status_code=400, detail="Invalid license_id")
    return lic


def license_is_compatible(parent, fork) -> bool:
    if not parent or not fork:
        return True

    if getattr(parent, "code", None) == "all_rights_reserved":
        return False

    restrictive = {"cc-by-nd", "cc-by-nc-nd"}
    permissive = {"cc-by", "cc0"}

    if getattr(parent, "code", None) in restrictive and getattr(fork, "code", None) in permissive:
        return False

    return True


# ----------------------------
# Safe Lineage Snapshot Upsert
# ----------------------------
async def ensure_lineage_snapshot(
    session: AsyncSession,
    *,
    recipe_id: int,
    root_recipe_id: int,
    depth: int,
):
    stmt = (
        insert(RecipeLineageSnapshot)
        .values(
            recipe_id=recipe_id,
            root_recipe_id=root_recipe_id,
            depth=depth,
        )
        .on_conflict_do_nothing(index_elements=["recipe_id"])
    )

    await session.execute(stmt)


# ----------------------------
# Bulk media insert helper
# ----------------------------
async def _insert_media_fast(session: AsyncSession, *, recipe_id: int, media_rows: List[dict]):
    if not media_rows:
        return

    # ensure recipe_id present
    for r in media_rows:
        r["recipe_id"] = recipe_id

    await session.execute(insert(RecipeMedia).values(media_rows))


# ----------------------------
# Helpers: upload single file -> returns (key, url)
# ----------------------------
async def _upload_file_and_resolve_url(
    *,
    file: UploadFile,
    user: User,
    key_prefix: str,
    max_size_mb: int,
    request: Request,
    recipe_id: int,
):
    """
    - Validate file size
    - Upload to storage.s3 (local or S3)
    - Return the (key, resolved_url)
    """
    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > max_size_mb:
        raise HTTPException(status_code=413, detail=f"File too large (> {max_size_mb} MB)")

    # extension (fallback to mime)
    if "." in file.filename:
        ext = file.filename.rsplit(".", 1)[-1].lower()
    else:
        # try mime map
        ext = file.content_type.split("/")[-1] if file.content_type else "bin"

    new_key = f"{key_prefix}/{recipe_id}/{uuid.uuid4().hex}.{ext}"

    bucket = os.getenv("S3_BUCKET_NAME")
    if not bucket:
        raise HTTPException(status_code=500, detail="Missing S3_BUCKET_NAME")

    debug_print(f"[media.upload] uploading {new_key} (size={size_mb:.2f}MB)", tag="MEDIA")

    extras = {"ContentType": file.content_type} if file.content_type else {}
    if not s3.is_local:
        extras["ACL"] = "public-read"

    # upload
    await s3.upload_fileobj(
        Fileobj=io.BytesIO(contents),
        Key=new_key,
        ExtraArgs=extras if extras else None,
    )

    # resolve url like avatar helper:

    url = f"/api/v1/media/{new_key}"

    return new_key, url


# ============================================================
# CREATE RECIPE (single-request: JSON + files)
# ============================================================
@router.post("/", status_code=201)
async def create_recipe(
    request: Request,
    data: str = Form(...),  # JSON recipe payload
    images: Optional[List[UploadFile]] = File(default=[]),
    videos: Optional[List[UploadFile]] = File(default=[]),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Accepts multipart/form-data:
        - data: JSON string -> CreateRecipeReq
        - images: repeated file fields
        - videos: repeated file fields

    Uploads files using your storage adapter, inserts recipe + media atomically.
    """
    if user.is_banned:
        raise HTTPException(status_code=403, detail="Account banned")

    # parse JSON
    try:
        payload = CreateRecipeReq(**json.loads(data))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid recipe JSON payload")

    # Basic validation
    if not payload.steps:
        raise HTTPException(status_code=400, detail="At least one step required")

    if len(payload.steps) > MAX_STEPS:
        raise HTTPException(status_code=400, detail="Too many steps")

    if len(payload.ingredients) > MAX_INGREDIENTS:
        raise HTTPException(status_code=400, detail="Too many ingredients")

    # Enforce media limits BEFORE uploading
    if len(images) > user.allowed_images_limit():
        raise HTTPException(status_code=400, detail="Too many images for your plan tier")

    if videos:
        if not user.plan_allows_videos():
            raise HTTPException(status_code=403, detail="Your plan does not allow video uploads")
        if len(videos) > user.allowed_videos_limit():
            raise HTTPException(status_code=400, detail="Too many videos for your plan tier")

    # License
    chosen_license = await _ensure_license(session, payload.license_id)

    # Create Recipe row and flush to get ID (we'll still use UUID keys, but having ID is fine)
    recipe = Recipe(
        author_id=user.id,
        title=payload.title.strip(),
        body=payload.body,
        parent_id=None,
        is_deleted=False,
        is_locked=False,
        is_draft=bool(payload.is_draft),
    )
    session.add(recipe)
    await session.flush()  # ensures recipe.id is populated

    # Insert ingredients and steps (bulk)
    session.add_all(
        [
            Ingredient(
                recipe_id=recipe.id,
                name=ing.name.strip(),
                is_animal=ing.is_animal,
                is_allergen=ing.is_allergen,
            )
            for ing in payload.ingredients
        ]
    )

    session.add_all(
        [
            RecipeStep(
                recipe_id=recipe.id,
                step_number=s.step_number,
                instruction=s.instruction.strip(),
                technique=s.technique,
                estimated_minutes=s.estimated_minutes or 0,
            )
            for s in sorted(payload.steps, key=lambda x: x.step_number)
        ]
    )

    # Now upload media files, collect media_rows. If uploads fail mid-way, attempt to delete already uploaded objects.
    bucket = os.getenv("S3_BUCKET_NAME")
    uploaded_keys = []
    media_rows = []
    position = 0

    try:
        # images
        for img in images:
            if not img.content_type or not img.content_type.startswith("image/"):
                raise HTTPException(status_code=400, detail=f"Unsupported image type: {img.content_type}")
            key, url = await _upload_file_and_resolve_url(
                file=img,
                user=user,
                key_prefix="recipes/images",
                max_size_mb=DEFAULT_MAX_IMAGE_MB,
                request=request,
                recipe_id=recipe.id
            )
            uploaded_keys.append(key)
            media_rows.append({"media_type": MediaType.IMAGE, "url": url, "position": position})
            position += 1

        # videos
        for vid in videos:
            if not vid.content_type or not vid.content_type.startswith("video/"):
                raise HTTPException(status_code=400, detail=f"Unsupported video type: {vid.content_type}")
            key, url = await _upload_file_and_resolve_url(
                file=vid,
                user=user,
                key_prefix="recipes/videos",
                max_size_mb=DEFAULT_MAX_VIDEO_MB,
                request=request,
                recipe_id=recipe.id
            )
            uploaded_keys.append(key)
            media_rows.append({"media_type": MediaType.VIDEO, "url": url, "position": position})
            position += 1

        # bulk insert media rows
        await _insert_media_fast(session, recipe_id=recipe.id, media_rows=media_rows)

    except Exception as exc:
        # try to delete uploaded objects (best-effort)
        try:
            if uploaded_keys and bucket:
                for k in uploaded_keys:
                    try:
                        await s3.delete_object(Key=k)
                    except Exception:
                        pass
        except Exception:
            pass

        # Re-raise as HTTPException if not already one
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=str(exc))

    # License binding
    if chosen_license:
        session.add(
            RecipeLicense(
                recipe_id=recipe.id,
                license_id=chosen_license.id,
                granted_by_user_id=user.id,
            )
        )

    # Lineage snapshot
    await ensure_lineage_snapshot(
        session,
        recipe_id=recipe.id,
        root_recipe_id=recipe.id,
        depth=0,
    )

    # Activity
    session.add(
        Activity(
            user_id=user.id,
            verb="recipe.create",
            subject_table="recipes",
            subject_id=recipe.id,
            payload=None,
        )
    )

    await session.commit()

    return {
        "ok": True,
        "recipe_id": recipe.id,
        "images_uploaded": len(images),
        "videos_uploaded": len(videos),
    }
