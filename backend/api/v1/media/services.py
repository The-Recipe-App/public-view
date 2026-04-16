import os
import io
import json
import boto3
import errno
import mimetypes
from botocore.config import Config
from botocore.exceptions import ClientError

# Local filesystem backed "S3-like" adapter for dev/testing.
class LocalS3LikeStorage:
    def __init__(self, base_path: str):
        self.base_path = base_path

    def _resolve_path(self, bucket: str, key: str):
        safe_bucket = bucket or "local-bucket"
        abs_dir = os.path.join(self.base_path, safe_bucket)
        os.makedirs(abs_dir, exist_ok=True)
        # normalize key to avoid absolute path escapes
        key = key.lstrip("/\\")
        return os.path.join(abs_dir, key)

    def get_object(self, Bucket: str, Key: str):
        path = self._resolve_path(Bucket, Key)
        if not os.path.exists(path):
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "Not found"}}, "GetObject")
        with open(path, "rb") as f:
            data = f.read()
        content_type, _ = mimetypes.guess_type(path)
        return {"Body": io.BytesIO(data), "ContentType": content_type or "application/octet-stream"}

    def upload_fileobj(self, Fileobj, Bucket: str, Key: str, ExtraArgs: dict = None):
        path = self._resolve_path(Bucket, Key)
        parent = os.path.dirname(path)
        os.makedirs(parent, exist_ok=True)
        # ensure we write bytes
        with open(path, "wb") as f:
            Fileobj.seek(0)
            f.write(Fileobj.read())
        # optionally write metadata sidecar (not required)
        meta = {}
        if ExtraArgs and "ContentType" in ExtraArgs:
            meta["ContentType"] = ExtraArgs["ContentType"]
        if meta:
            try:
                with open(path + ".meta", "w", encoding="utf-8") as mf:
                    json.dump(meta, mf)
            except Exception:
                pass
        return {"ETag": ""}

    def delete_object(self, Bucket: str, Key: str):
        path = self._resolve_path(Bucket, Key)
        try:
            os.remove(path)
        except FileNotFoundError:
            # mimic S3 delete: success even if missing
            return {"ResponseMetadata": {"HTTPStatusCode": 204}}
        except OSError as e:
            raise
        # remove sidecar if exists
        try:
            os.remove(path + ".meta")
        except Exception:
            pass
        return {"ResponseMetadata": {"HTTPStatusCode": 204}}


# Real S3 wrapper
class S3Storage:
    def __init__(self):
        cfg = Config(signature_version="s3v4")
        aws_key = os.getenv("S3_ACCESS_KEY_ID")
        aws_secret = os.getenv("S3_SECRET_ACCESS_KEY")
        endpoint = os.getenv("S3_ENDPOINT_URL")  # optional custom endpoint
        session_kwargs = {}
        if aws_key and aws_secret:
            session_kwargs["S3_ACCESS_KEY_ID"] = aws_key
            session_kwargs["S3_SECRET_ACCESS_KEY"] = aws_secret
        if endpoint:
            session_kwargs["endpoint_url"] = endpoint

        # client used for low-level operations
        self.client = boto3.client("s3", config=cfg, **session_kwargs)

    def get_object(self, Bucket: str, Key: str):
        return self.client.get_object(Bucket=Bucket, Key=Key)

    def upload_fileobj(self, Fileobj, Bucket: str, Key: str, ExtraArgs: dict = None):
        # boto3 client doesn't have upload_fileobj on client, but resource or s3transfer does.
        # Use client.put_object for simplicity here (works for most simple cases).
        Fileobj.seek(0)
        kwargs = {"Bucket": Bucket, "Key": Key, "Body": Fileobj.read()}
        if ExtraArgs:
            # map known extras
            if "ContentType" in ExtraArgs:
                kwargs["ContentType"] = ExtraArgs["ContentType"]
            if "ACL" in ExtraArgs:
                kwargs["ACL"] = ExtraArgs["ACL"]
        return self.client.put_object(**kwargs)

    def delete_object(self, Bucket: str, Key: str):
        return self.client.delete_object(Bucket=Bucket, Key=Key)


# Router that chooses which backend to use. Use FORCE_LOCAL=true to guarantee local.
class StorageRouter:
    def __init__(self):
        force_local = os.getenv("FORCE_LOCAL", "false").lower() == "true"
        backend = os.getenv("STORAGE_BACKEND", "local").lower()
        if force_local:
            backend = "local"

        if backend == "local":
            base_path = os.getenv("LOCAL_STORAGE_PATH", "./local_buckets")
            self.backend = LocalS3LikeStorage(base_path)
            self.is_local = True
        else:
            self.backend = S3Storage()
            self.is_local = False

    def get_object(self, **kwargs):
        return self.backend.get_object(**kwargs)

    def upload_fileobj(self, **kwargs):
        return self.backend.upload_fileobj(**kwargs)

    def delete_object(self, **kwargs):
        return self.backend.delete_object(**kwargs)

    def replace_object(self, *, Bucket: str, OldKey: str | None, NewKey: str, Fileobj, ExtraArgs: dict | None = None):
        # Upload new
        result = self.upload_fileobj(
            Fileobj=Fileobj,
            Bucket=Bucket,
            Key=NewKey,
            ExtraArgs=ExtraArgs,
        )

        # Delete old (best effort)
        if OldKey and OldKey != NewKey:
            try:
                self.delete_object(Bucket=Bucket, Key=OldKey)
            except Exception:
                pass  # never break upload if cleanup fails
        return result

s3 = StorageRouter()
