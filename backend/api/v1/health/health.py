# utilities/helpers/task_manager/health_router.py
#
# Provides three endpoints:
#
#   GET  /health               — lightweight liveness probe (always 200 if the
#                                process is up). Used by Railway / load balancers.
#
#   GET  /health/ready         — readiness probe. Returns 503 if the background
#                                scheduler has stalled or was never started.
#                                Use this as the target for k8s readinessProbe
#                                or Railway's health-check URL.
#
#   GET  /health/background    — detailed background-task health report. Returns
#                                the full HealthStatus payload so you can see
#                                task counts, last heartbeat, uptime, etc.
#                                Returns 503 when unhealthy so monitoring tools
#                                can alert on it without parsing the body.
#
# The /admin/background/restart endpoint from the original file has been
# deliberately removed — unauthenticated process-control routes are an easy
# way to DoS your own server (or hand an attacker a free restart loop).
# If you genuinely need it, gate it behind your admin auth dependency.

import platform
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from utilities.helpers.task_manager.manager import task_manager as bg_manager

health_router = APIRouter(tags=["Health"])

# Capture the process start time once at import so uptime is accurate even
# before the TaskManager is started (e.g. during the startup hook window).
_PROCESS_START = time.monotonic()


def _process_uptime() -> float:
    return round(time.monotonic() - _PROCESS_START, 2)


def _base_info() -> Dict[str, Any]:
    """Fields that every health endpoint includes."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "process_uptime_seconds": _process_uptime(),
    }


# ── Liveness ─────────────────────────────────────────────────────────────────


@health_router.get(
    "/health",
    summary="Liveness probe",
    description=(
        "Returns 200 as long as the Python process is alive and the event loop "
        "is not blocked. Does **not** check background-task health — use "
        "`/health/ready` for that. Suitable as a Railway / load-balancer "
        "liveness target."
    ),
    response_description="Process is alive",
)
async def health_liveness() -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content={
            **_base_info(),
            "status": "ok",
            "python": sys.version,
            "platform": platform.system(),
        },
    )


# ── Readiness ─────────────────────────────────────────────────────────────────


@health_router.get(
    "/health/ready",
    summary="Readiness probe",
    description=(
        "Returns 200 when the application is ready to serve traffic — i.e. the "
        "background scheduler is running and has heartbeated recently. "
        "Returns 503 if the scheduler has stalled or was never started. "
        "Use this as the Railway health-check URL or k8s readinessProbe target."
    ),
    response_description="Application is ready",
)
async def health_readiness() -> JSONResponse:
    healthy = bg_manager.is_healthy()
    status_code = 200 if healthy else 503

    body: Dict[str, Any] = {
        **_base_info(),
        "status": "ready" if healthy else "not_ready",
        "background_scheduler": "ok" if healthy else "stalled_or_not_started",
    }

    if not healthy:
        hs = bg_manager.get_health_status()
        body["last_heartbeat"] = hs.last_heartbeat
        body["scheduler_running"] = hs.scheduler_running
        # Don't expose last_error here — it may contain internal details.
        # The detailed endpoint /health/background is for that.

    return JSONResponse(status_code=status_code, content=body)


# ── Detailed background health ────────────────────────────────────────────────


@health_router.get(
    "/health/background",
    summary="Background task manager health (detailed)",
    description=(
        "Returns a full snapshot of the background TaskManager: heartbeat "
        "timestamp, uptime, per-state task counts, last recorded error, and "
        "the stall threshold. Returns HTTP 503 when unhealthy so alerting "
        "tools can trigger without body-parsing."
    ),
    response_description="Background scheduler health detail",
)
async def background_health() -> JSONResponse:
    hs = bg_manager.get_health_status()
    status_code = 200 if hs.is_healthy else 503

    body: Dict[str, Any] = {
        **_base_info(),
        "status": "healthy" if hs.is_healthy else "unhealthy",
        "scheduler_running": hs.scheduler_running,
        "last_heartbeat": hs.last_heartbeat,
        "stall_threshold_seconds": hs.stall_threshold_seconds,
        "uptime_seconds": hs.uptime_seconds,
        "task_counts": hs.task_counts,
        "total_tasks_in_registry": hs.total_tasks,
        # last_error is intentionally included here — this endpoint should
        # only be reachable by operators / internal monitoring, not public.
        "last_error": hs.last_error,
    }

    return JSONResponse(status_code=status_code, content=body)
