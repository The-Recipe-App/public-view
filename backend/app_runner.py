import os
import time
import uuid
import asyncio
import logging
import traceback
import multiprocessing

import uvicorn
import hypercorn
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


# ---------------- ENV ----------------

if os.path.exists(".env"):
    from dotenv import load_dotenv
    load_dotenv()

# default to production behavior
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"
from utilities.common.common_utility import debug_print

# ---------------- LOGGING ----------------

logger = logging.getLogger("forkit")

if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

logger.setLevel(logging.INFO if DEBUG_MODE else logging.WARNING)

# silence noisy libs
logging.getLogger("sqlalchemy").setLevel(logging.CRITICAL)
logging.getLogger("aiosqlite").setLevel(logging.CRITICAL)
logging.getLogger("boto3").setLevel(logging.CRITICAL)
logging.getLogger("botocore").setLevel(logging.CRITICAL)
logging.getLogger("s3transfer").setLevel(logging.CRITICAL)
logging.getLogger("python_multipart").setLevel(logging.CRITICAL)

# ---------------- APP IMPORT ----------------

from app.main import app

# ---------------- ERROR SCHEMA ----------------

def error_response(status_code: int, message: str, code: str = "error", details=None):
    payload = {
        "status": "error",
        "code": code,
        "message": message,
        "status_code": status_code,
    }
    if details:
        payload["details"] = details
    return JSONResponse(status_code=status_code, content=payload)

# ---------------- EXCEPTION HANDLERS ----------------

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if DEBUG_MODE:
        logger.warning("HTTP %s | %s | %s", exc.status_code, request.url.path, exc.detail)
    return error_response(
        status_code=exc.status_code,
        message=str(exc.detail),
        code="http_error",
    )

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    if DEBUG_MODE:
        logger.error("CRASH %s | %s\n%s", request.url.path, exc, traceback.format_exc())
    return error_response(
        status_code=500,
        message="Internal server error",
        code="internal_error",
    )

# ---------------- LOW-OVERHEAD MIDDLEWARE ----------------

@app.middleware("http")
async def log_request_timing(request: Request, call_next):
    if not DEBUG_MODE:
        return await call_next(request)

    request_id = uuid.uuid4().hex
    start = time.perf_counter()

    #logger.info("[%s] → %s %s", request_id, request.method, request.url.path)
    debug_print("[%s] → %s %s", request_id, request.method, request.url.path, tag="PERF", color="dim")

    response = await call_next(request)

    duration_ms = (time.perf_counter() - start) * 1000
    debug_print("[%s] %s %s (%.2f ms)", request_id, request.method, request.url.path, duration_ms, tag="PERF", color="dim")

    return response

# ---------------- UVICORN START ----------------

def get_uvicorn_config():
    """
    Platform-safe runtime configuration.
    Uses faster components if installed.
    """
    config = {
        "app": "app.main:app",  # import string required for workers
        "host": "0.0.0.0",
        "port": 8000,
        "proxy_headers": True,
        "forwarded_allow_ips": "*",
        "access_log": False,
    }

    # use high-performance runtime if available
    try:
        import uvloop  # noqa
        config["loop"] = "uvloop"
    except Exception:
        pass

    try:
        import httptools  # noqa
        config["http"] = "httptools"
    except Exception:
        pass

    return config


if __name__ == "__main__":
    multiprocessing.freeze_support()  # Windows-safe

    from hypercorn.config import Config
    from hypercorn.asyncio import serve
    
    port = os.getenv("PORT", 10000)

    config = Config()
    config.bind = ["0.0.0.0:{}".format(port)]
    config.proxy_headers = True
    config.accesslog = None  # disable access log
    config.errorlog = "-"    # stderr

    # use uvloop if available
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except ImportError:
        pass

    asyncio.run(serve(app, config))