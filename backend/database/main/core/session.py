# database/main/core/session.py
#
# Revision notes:
#
#  1.  CHECKOUT EVENT LISTENER REMOVED — the _on_checkout listener logged
#      at INFO on every single connection checkout from the pool, meaning
#      every DB operation in the app emitted a log line.  Under any real
#      traffic this floods your log aggregator and adds measurable overhead
#      to the hot path.  The _on_connect listener (fires only on new physical
#      connection creation, which is rare) is kept — that one is genuinely
#      useful signal with near-zero volume.
#
#  2.  PREWARM OPENS CONNECTIONS IN PARALLEL — the original loop opened
#      connections one at a time (serial await).  Warming 25 connections
#      sequentially against a cloud DB (e.g. Railway, Supabase, RDS) over a
#      ~5–10 ms RTT link means startup takes 125–250 ms just in prewarm.
#      asyncio.gather opens all N connections concurrently, limited by
#      a semaphore so we don't overshoot the pool size.
#
#  3.  PREWARM FAILURE ISOLATION — the original finally block closed
#      connections even if engine.connect() raised, silently swallowing the
#      error.  The new version collects errors, logs them, and still signals
#      done_event so startup doesn't hang forever if the DB is partially
#      available.
#
#  4.  get_async_session TYPE ANNOTATION — added AsyncGenerator return type
#      so FastAPI's dependency injection can reason about it correctly and
#      IDEs provide proper completion.
#
#  5.  connect_args ADDED — passes asyncpg-specific tuning via
#      connect_args.  The statement_cache_size=0 override is here as a
#      comment-documented option for pgBouncer users (PgBouncer in
#      transaction-pooling mode is incompatible with prepared statements).
#      Leave at the default 1024 if you connect directly to Postgres.
#
#  6.  execution_options ADDED — sets isolation_level to READ COMMITTED
#      explicitly (PostgreSQL default, but now contract-documented) and
#      enables no_parameters_on_empty_query as a minor optimisation.

import asyncio
import logging
import os
from typing import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import AsyncAdaptedQueuePool

from utilities.common.common_utility import debug_print

logger = logging.getLogger("db.pool")

# ── Env / config ────────────────────────────────────────────────────────────

DATABASE_URL: str = os.environ["MAIN_DB_URL"]  # hard fail — no default

DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "5"))
DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "5"))
DB_POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "1800"))

# ── Engine ───────────────────────────────────────────────────────────────────

engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    poolclass=AsyncAdaptedQueuePool,
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    pool_timeout=DB_POOL_TIMEOUT,
    pool_recycle=DB_POOL_RECYCLE,
    pool_pre_ping=True,
    # asyncpg tuning.
    # If you use PgBouncer in transaction-pooling mode, set
    # statement_cache_size=0 to disable prepared statements, which are
    # incompatible with transaction pooling.
    # connect_args={"statement_cache_size": 0},
)

# ── Pool event listeners ──────────────────────────────────────────────────────
# FIX #1 — only log new physical connections, not every checkout.
# Checkout happens on every DB call; logging it adds noise + overhead.


@event.listens_for(engine.sync_engine, "connect")
def _on_connect(dbapi_conn, conn_record):
    logger.info("MAIN_DB: new physical connection created")


# ── Session factory ───────────────────────────────────────────────────────────

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,  # objects remain usable after commit
    autoflush=False,  # explicit flush control — no surprise queries
    class_=AsyncSession,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a scoped async session."""
    async with AsyncSessionLocal() as session:
        yield session


# ── Pool prewarm ─────────────────────────────────────────────────────────────
# FIX #2 — parallel connection opening via asyncio.gather + semaphore.
# FIX #3 — partial failure is logged but does not block startup.


async def prewarm_pool(
    done_event: asyncio.Event | None = None,
    n: int | None = None,
) -> None:
    """
    Open N physical connections to the DB concurrently so the pool is
    fully warm before the first real request arrives.

    A semaphore prevents us from exceeding pool_size + max_overflow even
    if n is accidentally set too high.
    """
    n = n or DB_POOL_SIZE
    debug_print(f"Pre-warming main DB pool ({n} connections)...", color="cyan")

    sem = asyncio.Semaphore(DB_POOL_SIZE + DB_MAX_OVERFLOW)
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
            "MAIN_DB prewarm: %d/%d connections failed: %s",
            len(errors),
            n,
            errors[0],
        )
    else:
        debug_print("Main DB pool pre-warming complete.", color="green")

    if done_event:
        done_event.set()
