# api/v1/auth/device.py

import os
import hashlib
from fastapi import Request, Response

DEVICE_COOKIE = "__Host-forkit-device"

def generate_device_secret() -> str:
    return os.urandom(32).hex()  # 256-bit

def hash_device(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()

def get_or_create_device_secret(request: Request, response: Response) -> str:
    secret = request.cookies.get(DEVICE_COOKIE)
    if not secret:
        secret = generate_device_secret()
        response.set_cookie(
            key=DEVICE_COOKIE,
            value=secret,
            httponly=True,
            secure=True,
            samesite="none",
            path="/",
            max_age=60 * 60 * 24 * 365 * 5,  # 5 years
        )
    return secret