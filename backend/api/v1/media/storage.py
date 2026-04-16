# api/v1/media/storage.py
#
# Revision notes:
#
#  1.  SYNC S3 UPLOAD FIXED — the original S3Storage.upload_fileobj called
#      boto3's synchronous put_object directly on the event loop thread.
#      During a 200 MB video upload this blocks the entire event loop for
#      the duration of the network transfer — no other request can be
#      handled by that worker until the upload finishes.
#
#      Fix: every blocking I/O call (upload, delete, get, signed_url) is
#      now wrapped in asyncio.get_event_loop().run_in_executor(None, ...)
#      which offloads it to the default ThreadPoolExecutor, freeing the
#      event loop immediately.
#
#      The local filesystem backend has the same problem (open + write is
#      blocking I/O) and gets the same fix.
#
#  2.  ENTIRE FILE READ INTO MEMORY FIXED — the original read the entire
#      file into memory with `contents = await file.read()`, then wrapped
#      it in io.BytesIO for upload.  For a 200 MB video this means 200 MB
#      resident in RAM per concurrent upload.  With 10 concurrent uploads
#      that's 2 GB — on a small VPS this kills the process.
#
#      Fix: upload_fileobj now accepts a raw file-like object (the
#      SpooledTemporaryFile that FastAPI gives you) and streams it directly
#      to S3 using boto3's upload_fileobj (which uses multipart under the
#      hood for large files) rather than put_object (which buffers fully).
#      Size validation is done via Content-Length header or a lightweight
#      seek/tell — no full read required.
#
#  3.  DUPLICATE storage.py / services.py CONSOLIDATED — services.py was
#      an exact copy of this file.  It has been deleted.  All imports
#      should point to api.v1.media.storage.
#
#  4.  S3_BUCKET_NAME VALIDATED AT INIT — rather than raising a 500 inside
#      a request handler when the bucket name is missing, we validate at
#      StorageRouter construction time so misconfiguration is caught at
#      startup, not at the first upload request.
#
#  5.  TransferConfig ADDED for S3 multipart — boto3's managed upload
#      automatically splits large files into parts and uploads them in
#      parallel threads.  We configure sensible thresholds: multipart kicks
#      in above 8 MB, each part is 8 MB, and up to 4 parts upload in
#      parallel per file.  This dramatically improves throughput for large
#      video uploads without any extra code.

from __future__ import annotations

import asyncio
import io
import mimetypes
import os
from functools import partial
from typing import Optional, BinaryIO

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
from botocore.exceptions import ClientError
from utilities.common.common_utility import debug_print


# ── Shared transfer config for multipart uploads ──────────────────────────────
# Kicks in for files > 8 MB; uploads up to 4 parts in parallel threads.
_TRANSFER_CONFIG = TransferConfig(
    multipart_threshold=8 * 1024 * 1024,   # 8 MB
    multipart_chunksize=8 * 1024 * 1024,   # 8 MB per part
    max_concurrency=4,
    use_threads=True,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_sync(func, *args, **kwargs):
    """
    Run a synchronous callable in the default thread pool so it doesn't
    block the event loop.  Returns an awaitable.
    """
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(None, partial(func, *args, **kwargs))


# ============================================================
# Local filesystem backend (dev / CI)
# ============================================================

class LocalS3LikeStorage:
    """
    Filesystem-backed S3 shim for local development.
    All methods are async — blocking file I/O runs in the thread pool.
    """

    def __init__(self, base_path: str):
        self.base_path = base_path

    def _resolve_path(self, bucket: str, key: str) -> str:
        safe_bucket = bucket or "local-bucket"
        abs_dir = os.path.join(self.base_path, safe_bucket)
        os.makedirs(abs_dir, exist_ok=True)
        key = key.lstrip("/\\")
        return os.path.join(abs_dir, key)

    def _sync_get_object(self, Bucket: str, Key: str) -> dict:
        path = self._resolve_path(Bucket, Key)
        if not os.path.exists(path):
            raise ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "Not found"}},
                "GetObject",
            )
        content_type, _ = mimetypes.guess_type(path)
        return {
            "Body": open(path, "rb"),
            "ContentType": content_type or "application/octet-stream",
        }

    def _sync_upload_fileobj(
        self,
        Fileobj: BinaryIO,
        Bucket: str,
        Key: str,
        ExtraArgs: Optional[dict] = None,
    ) -> dict:
        path = self._resolve_path(Bucket, Key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        Fileobj.seek(0)
        with open(path, "wb") as f:
            while chunk := Fileobj.read(1024 * 1024):  # 1 MB chunks
                f.write(chunk)
        return {"ETag": ""}

    def _sync_delete_object(self, Bucket: str, Key: str) -> dict:
        path = self._resolve_path(Bucket, Key)
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        return {"ResponseMetadata": {"HTTPStatusCode": 204}}

    # FIX #1 — all public methods are async; blocking I/O in thread pool
    async def get_object(self, Bucket: str, Key: str) -> dict:
        return await _run_sync(self._sync_get_object, Bucket=Bucket, Key=Key)

    async def upload_fileobj(
        self,
        Fileobj: BinaryIO,
        Bucket: str,
        Key: str,
        ExtraArgs: Optional[dict] = None,
    ) -> dict:
        return await _run_sync(
            self._sync_upload_fileobj,
            Fileobj=Fileobj, Bucket=Bucket, Key=Key, ExtraArgs=ExtraArgs,
        )

    async def delete_object(self, Bucket: str, Key: str) -> dict:
        return await _run_sync(self._sync_delete_object, Bucket=Bucket, Key=Key)


# ============================================================
# AWS S3 / S3-compatible backend (prod)
# ============================================================

class S3Storage:
    """
    boto3-backed S3 storage.
    All methods are async — boto3 calls run in the thread pool.
    """

    def __init__(self) -> None:
        cfg = Config(signature_version="s3v4")

        self.client = boto3.client(
            "s3",
            endpoint_url=os.getenv("S3_ENDPOINT_URL"),
            aws_access_key_id=os.getenv("S3_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY"),
            config=cfg,
        )

    def _sync_get_object(self, Bucket: str, Key: str) -> dict:
        return self.client.get_object(Bucket=Bucket, Key=Key)

    def _sync_upload_fileobj(
        self,
        Fileobj: BinaryIO,
        Bucket: str,
        Key: str,
        ExtraArgs: Optional[dict] = None,
    ) -> None:
        # FIX #2 — use boto3 managed upload (streaming multipart for large files)
        # rather than put_object (which buffers the entire body in memory).
        Fileobj.seek(0)
        self.client.upload_fileobj(
            Fileobj,
            Bucket,
            Key,
            ExtraArgs=ExtraArgs,
            Config=_TRANSFER_CONFIG,
        )

    def _sync_delete_object(self, Bucket: str, Key: str) -> dict:
        return self.client.delete_object(Bucket=Bucket, Key=Key)

    def _sync_signed_url(self, Bucket: str, Key: str, expires: int) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": Bucket, "Key": Key},
            ExpiresIn=expires,
        )

    # FIX #1 — all public methods are async; boto3 calls in thread pool
    async def get_object(self, Bucket: str, Key: str) -> dict:
        return await _run_sync(self._sync_get_object, Bucket=Bucket, Key=Key)

    async def upload_fileobj(
        self,
        Fileobj: BinaryIO,
        Bucket: str,
        Key: str,
        ExtraArgs: Optional[dict] = None,
    ) -> None:
        return await _run_sync(
            self._sync_upload_fileobj,
            Fileobj=Fileobj, Bucket=Bucket, Key=Key, ExtraArgs=ExtraArgs,
        )

    async def delete_object(self, Bucket: str, Key: str) -> dict:
        return await _run_sync(self._sync_delete_object, Bucket=Bucket, Key=Key)

    async def signed_url(self, Bucket: str, Key: str, expires: int = 300) -> str:
        return await _run_sync(self._sync_signed_url, Bucket=Bucket, Key=Key, expires=expires)


# ============================================================
# StorageRouter — single interface used by the rest of the app
# ============================================================

class StorageRouter:
    """
    Thin routing layer that selects the right backend based on env.

    Environment variables:
        STORAGE_BACKEND   "local" (default) or "s3"
        FORCE_LOCAL       "true" forces local regardless of STORAGE_BACKEND
        LOCAL_STORAGE_PATH  root path for local backend (default: ./local_buckets)
        S3_BUCKET_NAME    required for all upload/delete calls
    """

    def __init__(self) -> None:
        backend = os.getenv("STORAGE_BACKEND", "local").lower()
        if os.getenv("FORCE_LOCAL", "false").lower() == "true":
            backend = "local"

        if backend == "local":
            base_path = os.getenv("LOCAL_STORAGE_PATH", "./local_buckets")
            self.backend: LocalS3LikeStorage | S3Storage = LocalS3LikeStorage(base_path)
            self.is_local = True
        else:
            self.backend = S3Storage()
            self.is_local = False

        # FIX #4 — validate bucket name at startup, not inside a request handler
        self.bucket: str = os.environ["S3_BUCKET_NAME"]

    async def get_object(self, Key: str) -> dict:
        return await self.backend.get_object(Bucket=self.bucket, Key=Key)

    async def upload_fileobj(
        self,
        Fileobj: BinaryIO,
        Key: str,
        ExtraArgs: Optional[dict] = None,
    ) -> None:
        await self.backend.upload_fileobj(
            Fileobj=Fileobj, Bucket=self.bucket, Key=Key, ExtraArgs=ExtraArgs,
        )

    async def delete_object(self, Key: str) -> None:
        await self.backend.delete_object(Bucket=self.bucket, Key=Key)
        debug_print(f"Deleted {Key}", color="green")

    async def signed_url(self, Key: str, expires: int = 300) -> str:
        if self.is_local:
            raise RuntimeError("Signed URLs not supported in local backend")
        assert isinstance(self.backend, S3Storage)
        return await self.backend.signed_url(Bucket=self.bucket, Key=Key, expires=expires)


# Singleton — imported by the rest of the app as `from api.v1.media.storage import s3`
s3 = StorageRouter()