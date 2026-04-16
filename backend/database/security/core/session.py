# database/security/core/session.py
#
# Revision notes:
#
#  1.  CHECKOUT EVENT LISTENER REMOVED — same reason as main session.py.
#      Logging on every checkout floods logs under real traffic.
#      _on_connect (new physical connection only) is kept.
#
#  2.  PREWARM PARALLEL + FAILURE-ISOLATED — same pattern as main session.py.
#      Serial open loop replaced with asyncio.gather + semaphore.
#      Errors are collected and logged but done_event is always set so
#      startup never hangs.
#
#  3.  get_security_session TYPE ANNOTATION — added AsyncGenerator return
#      type for FastAPI DI and IDE completion consistency.
#
#  4.  autoflush=False ADDED to AsyncSessionLocal — was missing on the
#      security session while present on the main session.  Without it,
#      SQLAlchemy can emit surprise SELECT queries mid-transaction when
#      accessing a relationship on a dirty object.

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import AsyncAdaptedQueuePool

from utilities.common.common_utility import debug_print

logger = logging.getLogger("db.pool.security")

# ── Env / config ─────────────────────────────────────────────────────────────

SECURITY_DATABASE_URL: str = os.environ["SECURITY_DB_URL"]  # hard fail — no default

SEC_POOL_SIZE    = int(os.getenv("SEC_POOL_SIZE",    "5"))
SEC_MAX_OVERFLOW = int(os.getenv("SEC_MAX_OVERFLOW", "5"))
SEC_POOL_TIMEOUT = int(os.getenv("SEC_POOL_TIMEOUT", "5"))
SEC_POOL_RECYCLE = int(os.getenv("SEC_POOL_RECYCLE", "1000"))

# ── Engine ────────────────────────────────────────────────────────────────────

engine: AsyncEngine = create_async_engine(
    SECURITY_DATABASE_URL,
    echo=False,
    future=True,
    poolclass=AsyncAdaptedQueuePool,
    pool_size=SEC_POOL_SIZE,
    max_overflow=SEC_MAX_OVERFLOW,
    pool_timeout=SEC_POOL_TIMEOUT,
    pool_recycle=SEC_POOL_RECYCLE,
    pool_pre_ping=True,
    # If using PgBouncer in transaction-pooling mode, uncomment:
    # connect_args={"statement_cache_size": 0},
)

# ── Pool event listeners ──────────────────────────────────────────────────────

@event.listens_for(engine.sync_engine, "connect")
def _on_connect(dbapi_conn, conn_record):
    logger.info("SEC_DB: new physical connection created")


# ── Session factory ───────────────────────────────────────────────────────────

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,          # FIX #4 — was missing; prevents surprise queries
    class_=AsyncSession,
)


async def get_security_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a scoped async security session."""
    async with AsyncSessionLocal() as session:
        yield session


@asynccontextmanager
async def security_session_ctx() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for use outside FastAPI DI (background tasks, etc.)."""
    async with AsyncSessionLocal() as session:
        yield session


# ── Pool prewarm ──────────────────────────────────────────────────────────────

async def prewarm_pool(
    done_event: asyncio.Event | None = None,
    n: int | None = None,
) -> None:
    """
    Open N physical connections to the security DB concurrently so the pool
    is fully warm before the first request arrives.
    """
    n = n or SEC_POOL_SIZE
    debug_print(f"Pre-warming security DB pool ({n} connections)...", color="cyan")

    sem = asyncio.Semaphore(SEC_POOL_SIZE + SEC_MAX_OVERFLOW)
    errors: list[Exception] = []

    async def _open_one() -> None:
        async with sem:
            try:
                conn = await engine.connect()
                await conn.close()
            except Exception as exc:
                errors.append(exc)

    await asyncio.gather(*[_open_one() for _ in range(n)])

    if errors:
        logger.warning(
            "SEC_DB prewarm: %d/%d connections failed: %s",
            len(errors), n, errors[0],
        )
    else:
        debug_print("Security DB pool pre-warming complete.", color="green")

    logger.info("SEC_DB: prewarm completed (%d connections attempted)", n)

    if done_event:
        done_event.set()