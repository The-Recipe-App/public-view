import io
import os
import uuid
import re
from datetime import datetime, timezone

from fastapi import HTTPException, UploadFile, Request, status

from sqlalchemy.ext.asyncio import AsyncSession
from database.main.core.models import User

from api.v1.media.storage import s3
from utilities.common.common_utility import debug_print

from utilities.helpers.task_manager.manager import task_manager, TaskType


MAX_AVATAR_SIZE_MB = 5 * 1024 * 1024 # 5 MB
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}


# ============================================================
# Avatar Key Resolver
# ============================================================

def fetch_user_avatar_key(user: User) -> str | None:
    return getattr(user, "avatar_key", None)


# ============================================================
# Upload Handler (Zero Cache, Storage-Only)
# ============================================================

async def handle_avatar_upload(
    *,
    request: Request,
    user: User,
    session: AsyncSession,
    file: UploadFile,
):
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Unsupported image type",
        )

    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)

    if size_mb > MAX_AVATAR_SIZE_MB:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "Avatar too large",
        )

    ext = file.filename.rsplit(".", 1)[-1].lower()
    new_key = f"avatars/{user.id}/{uuid.uuid4()}.{ext}"

    bucket = os.getenv("S3_BUCKET_NAME")
    if not bucket:
        raise HTTPException(500, "Missing S3_BUCKET_NAME")

    debug_print(f"[avatar] uploading {new_key}", tag="MEDIA")

    extras = {"ContentType": file.content_type}
    if not s3.is_local:
        extras["ACL"] = "public-read"

    # Upload
    await s3.upload_fileobj(
        Fileobj=io.BytesIO(contents),
        Key=new_key,
        ExtraArgs=extras if not s3.is_local else None,
    )

    # Delete old avatar (best effort)
    if user.avatar_key and user.avatar_key != new_key:
        try:
            await task_manager.add_task(func=s3.delete_object, args=(user.avatar_key,), run_once_and_forget=True, task_type=TaskType.ASYNC)
        except Exception:
            pass

    # URL resolution
    scheme = request.url.scheme
    host = request.headers.get("host")

    _is_local = re.match(r'^(0\.0\.0\.0|127\.0\.0\.1|localhost)(:\d+)?$', host)
    _base = 'localhost' + host.split(':')[1] if _is_local else host

    avatar_url = f"{scheme}://{_base}/api/v1/media/avatars/{user.id}"

    updated_at = datetime.now(timezone.utc)

    # Persist
    user.avatar_key = new_key
    user.avatar_url = avatar_url
    user.avatar_changed_at = updated_at
    await session.commit()

    return {
        "ok": True,
        "avatar_url": avatar_url,
        "avatar_changed_at": updated_at,
    }
