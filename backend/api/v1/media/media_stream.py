import hashlib
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse, RedirectResponse, Response

from botocore.exceptions import ClientError
from api.v1.media.storage import s3

import httpx


# ============================================================
# Avatar Streaming / Redirect Layer
# ============================================================

SIGNED_URL_TTL = 300  # seconds


def avatar_etag(key: str) -> str:
    """Stable ETag based on avatar key."""
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


async def stream_avatar(bucket: str, key: str):
    """
    True streaming response:
    - No buffering
    - No byte caching
    """
    try:
        obj = await s3.get_object(Key=key)

        body = obj["Body"]
        content_type = obj.get("ContentType") or "application/octet-stream"

        return StreamingResponse(
            body,
            media_type=content_type,
            headers={
                "Cache-Control": "public, max-age=3600, stale-while-revalidate=86400"
            },
        )

    except ClientError:
        raise HTTPException(status_code=404, detail="Avatar not found")
    except Exception as e:
        raise HTTPException(status_code=502, detail="Storage error")


async def redirect_avatar(bucket: str, key: str):
    """
    Production fastest path:
    Redirect to signed URL (no backend streaming).
    """
    try:
        url = await s3.signed_url(
            Key=key,
            expires=SIGNED_URL_TTL,
        )
        return RedirectResponse(url=url, status_code=302)
    except Exception as e:
        print(e)
        raise HTTPException(status_code=502, detail="Signed URL generation failed")


async def avatar_response(
    *,
    request: Request,
    bucket: str,
    key: str,
):
    """
    Unified avatar delivery:
    - Local backend → stream
    - S3 backend → redirect signed URL
    - Supports conditional GET (304)
    """
    try:
        etag = avatar_etag(key)

        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304)

        if s3.is_local:
            resp = await stream_avatar(bucket=bucket, key=key)
        else:
            resp = await redirect_avatar(bucket=bucket, key=key)

        resp.headers["ETag"] = etag
        resp.headers["Cache-Control"] = (
            "public, max-age=3600, stale-while-revalidate=86400"
        )

        return resp
    except Exception as e:
        print(e)
        raise

# ============================================================
# Recipe Media Streaming / Redirect Layer
# ============================================================

def recipe_media_etag(key: str) -> str:
    """
    Stable ETag based on recipe media key.
    """
    return hashlib.sha1(f"recipe:{key}".encode("utf-8")).hexdigest()


async def stream_recipe_media(key: str):
    """
    True streaming response for recipe images/videos.
    """
    try:
        obj = await s3.get_object(Key=key)

        body = obj["Body"]
        content_type = obj.get("ContentType") or "application/octet-stream"

        return StreamingResponse(
            body,
            media_type=content_type,
            headers={
                "Cache-Control": "public, max-age=3600, stale-while-revalidate=86400"
            },
        )

    except ClientError as e:
        raise HTTPException(status_code=404, detail="Recipe media not found")
    except Exception:
        raise HTTPException(status_code=502, detail="Storage error")


async def redirect_recipe_media(key: str):
    """
    Production fastest path:
    Redirect to signed URL.
    """
    try:
        url = await s3.signed_url(
            Key=key,
            expires=SIGNED_URL_TTL,
        )
        return RedirectResponse(url=url, status_code=302)
    except Exception:
        raise HTTPException(status_code=502, detail="Signed URL generation failed")


async def recipe_media_response(
    *,
    request: Request,
    key: str,
):
    """
    Unified recipe media delivery with proper browser caching.
    - Local backend → stream
    - S3 backend → proxy through backend (enables Cache-Control headers)
    - Supports conditional GET (304)
    """
    etag = recipe_media_etag(key)
    key = f'recipes/{key}'

    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)

    if s3.is_local:
        resp = await stream_recipe_media(key=key)
        resp.headers["ETag"] = etag
        resp.headers["Cache-Control"] = "public, max-age=3600, stale-while-revalidate=86400"
        return resp

    # S3/Tigris: proxy through backend so we control cache headers
    try:
        url = await s3.signed_url(Key=key, expires=SIGNED_URL_TTL)
        async with httpx.AsyncClient() as client:
            r = await client.get(url)
            r.raise_for_status()

        return Response(
            content=r.content,
            media_type=r.headers.get("content-type", "image/jpeg"),
            headers={
                "Cache-Control": "public, max-age=86400, stale-while-revalidate=604800",
                "ETag": etag,
            }
        )
    except Exception as e:
        print(e)
        raise HTTPException(status_code=502, detail="Media fetch failed")