import sys
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

from pathlib import Path
import os

from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.lifespan import lifespan
from api.v1.router import v1_router
from api.v1.admin.admin import setup_admin
from api.v1.auth.utils.dependencies import get_current_user_admin_core
from api.legal.legal import router as legal_router

from database.main.core.session import AsyncSessionLocal
from utilities.common.common_utility import debug_print

# ---------------- APP ----------------

app = FastAPI(
    lifespan=lifespan,
    title="Forkit - Core Systems Interface",
    version="1.0.0",
)

# ---------------- CORS ----------------
# Exact origins = faster preflight handling

_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173")
_ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ---------------- STATIC FILES ----------------

BASE_DIR = Path(__file__).resolve().parents[1]

app.mount(
    "/static",
    StaticFiles(directory=BASE_DIR / "app" / "static"),
    name="static",
)

# ---------------- ADMIN PROTECTION (optimized) ----------------

ADMIN_PREFIX = "/admin"
SEARCH_PREFIX = "/api/v1/search"

@app.middleware("http")
async def protect_routes(request: Request, call_next):
    path = request.url.path

    if path.startswith(SEARCH_PREFIX):
        if not request.app.state.model_ready.is_set():
            return JSONResponse(
                status_code=503,
                content={"detail": "Search is temporarily unavailable. Model is still loading."},
            )
        return await call_next(request)

    if not path.startswith(ADMIN_PREFIX):
        return await call_next(request)

    try:
        async with AsyncSessionLocal() as session:
            user = await get_current_user_admin_core(
                request=request,
                session=session,
            )

        if not user.is_admin:
            return Response(status_code=404)

    except HTTPException:
        return Response(status_code=404)

    except Exception as e:
        debug_print(f"[ADMIN_MW] ERROR: {type(e).__name__}: {e}")
        return Response(status_code=404)

    return await call_next(request)

# ---------------- ROUTERS ----------------

app.include_router(v1_router, prefix="/api")
app.include_router(legal_router, prefix="/api")

setup_admin(app)

# ---------------- ROOT ----------------

@app.get("/")
async def root():
    return {"message": "Hello World"}