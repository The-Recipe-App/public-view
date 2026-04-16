# security/firewall/rate_limit.py
#
# Sliding-window rate limiter backed by PostgreSQL.
# No Redis, no extra services, no extra cost.
#
# ── Why Postgres instead of Redis ────────────────────────────────────────────
#
#   The original in-process defaultdict(deque) + asyncio.Lock was broken
#   across multiple Uvicorn workers — each process had its own independent
#   counter, so a limit of 60/min silently became 240/min with 4 workers.
#
#   Redis would fix that but costs money and adds operational overhead for
#   a solo dev / early-stage startup.
#
#   PostgreSQL is already running, already paid for, and is more than fast
#   enough for rate limiting on sensitive routes (auth, OTP, registration).
#   These endpoints already do 2–5 DB round-trips anyway; one extra call
#   at ~2ms is not the bottleneck.
#
# ── How it works ─────────────────────────────────────────────────────────────
#
#   Table: rate_limit_hits  (lives in the security DB)
#     - One row per (key, hit_id) pair.
#     - hit_id is a client-generated UUID so concurrent inserts from
#       different workers never collide.
#     - expires_at = now + window.  A periodic cleanup task deletes
#       expired rows so the table stays small.
#
#   Per request — single atomic CTE, one round-trip:
#     1. DELETE rows WHERE key = $key AND expires_at < now()   (evict stale)
#     2. INSERT a new row for this hit
#     3. SELECT COUNT(*) WHERE key = $key                      (current usage)
#     4. If count > limit → DELETE the row just inserted       (undo + block)
#
#   Because this is a single SQL statement (writeable CTE), there is no
#   TOCTOU race between concurrent workers hitting the same key.
#
# ── Schema (add to your Alembic migration) ───────────────────────────────────
#
#   CREATE TABLE rate_limit_hits (
#       key        VARCHAR(255) NOT NULL,
#       hit_id     UUID         NOT NULL,
#       expires_at TIMESTAMPTZ  NOT NULL,
#       PRIMARY KEY (key, hit_id)
#   );
#   CREATE INDEX ix_rate_limit_hits_key_expires
#       ON rate_limit_hits (key, expires_at);
#
#   The table stays tiny in practice — every check evicts its own stale
#   rows first, and cleanup_expired() runs every 5 minutes via TaskManager.
#
# ── Failure behaviour ─────────────────────────────────────────────────────────
#
#   If the DB call fails (pool exhausted, network blip, etc.) the limiter
#   FAILS OPEN — it logs a warning and allows the request.  The reasoning:
#   a DB hiccup at the rate-limit layer should not cascade into a full API
#   outage.  Your real protection in that scenario is the Cerberus engine
#   + block cache, which is already in memory and unaffected.

from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database.security.core.session import security_session_ctx
from database.security.core.models import RateLimitHits

logger = logging.getLogger("firewall.rate_limit")

# ── SQL ───────────────────────────────────────────────────────────────────────
#
# Single-statement sliding window using a writeable CTE.
#
#   evict    → delete stale hits for this key (shrinks window to [now-W, now])
#   ins      → record this hit with TTL = now + window
#   hit_count→ count all live hits including the one we just inserted
#   cleanup  → if over limit, delete the hit we just inserted (undo the insert)
#
# Returns the hit count after eviction (including this request if allowed,
# excluding it if blocked).  Caller compares to limit.

_SLIDING_WINDOW_SQL = text(
"""
WITH
    evict AS (
        DELETE FROM rate_limit_hits
        WHERE  key        = :key
        AND  expires_at < NOW()
    ),
    ins AS (
        INSERT INTO rate_limit_hits (key, hit_id, expires_at)
        VALUES (:key, :hit_id, NOW() + :window * INTERVAL '1 second')
    ),
    hit_count AS (
        SELECT COUNT(*) AS n
        FROM   rate_limit_hits
        WHERE  key = :key
    ),
    cleanup AS (
        DELETE FROM rate_limit_hits
        WHERE  key    = :key
        AND  hit_id = :hit_id
        AND  (SELECT n FROM hit_count) > :limit
    )
SELECT (SELECT n FROM hit_count) AS n
"""
)

_CLEANUP_ALL_EXPIRED_SQL = text(
"""
DELETE FROM rate_limit_hits WHERE expires_at < NOW()
"""
)


# ── Public API ────────────────────────────────────────────────────────────────


async def hit_rate_limit(
    key: str,
    limit: int,
    window: float,
    *,
    session: Optional[AsyncSession] = None,
) -> bool:
    """
    Atomic sliding-window rate limiter backed by PostgreSQL.

    Args:
        key:     Unique identity key, e.g. "login:1.2.3.4" or "otp:1.2.3.4:fpXYZ"
        limit:   Max requests allowed within the rolling window
        window:  Rolling window size in seconds
        session: Optional existing AsyncSession.  If not provided, a new
                security DB session is opened for this call.

    Returns:
        True  → request is allowed (under limit)
        False → rate limit exceeded

    On DB error: logs a warning and returns True (fail-open).
    """
    hit_id = str(uuid.uuid4())

    async def _run(s: AsyncSession) -> bool:
        result = await s.execute(
            _SLIDING_WINDOW_SQL,
            {"key": key, "hit_id": hit_id, "window": window, "limit": limit},
        )
        await s.commit()
        row = result.fetchone()
        count = int(row.n) if row else 0
        return count <= limit

    try:
        if session is not None:
            return await _run(session)
        async with security_session_ctx() as s:
            return await _run(s)
    except Exception as exc:
        logger.warning(
            "rate_limit: DB error, failing open for key=%r: %s",
            key,
            exc,
        )
        return True  # fail-open — see module docstring


async def get_current_usage(
    key: str,
    window: float,
    *,
    session: Optional[AsyncSession] = None,
) -> int:
    """
    Return the number of hits in the current window for a key.
    Useful for Retry-After headers or a rate-limit debug dashboard.
    Returns 0 on DB error.
    """
    sql = text(
        """
        SELECT COUNT(*) AS n
        FROM   rate_limit_hits
        WHERE  key        = :key
          AND  expires_at > NOW() - :window * INTERVAL '1 second'
    """
    )

    async def _run(s: AsyncSession) -> int:
        result = await s.execute(sql, {"key": key, "window": window})
        row = result.fetchone()
        return int(row.n) if row else 0

    try:
        if session is not None:
            return await _run(session)
        async with security_session_ctx() as s:
            return await _run(s)
    except Exception as exc:
        logger.warning(
            "rate_limit: get_current_usage DB error for key=%r: %s", key, exc
        )
        return 0


async def reset_key(
    key: str,
    *,
    session: Optional[AsyncSession] = None,
) -> None:
    """
    Clear all recorded hits for a key immediately.
    Used in tests and in manual unban / unlock flows.
    """
    sql = text("DELETE FROM rate_limit_hits WHERE key = :key")

    async def _run(s: AsyncSession) -> None:
        await s.execute(sql, {"key": key})
        await s.commit()

    try:
        if session is not None:
            await _run(session)
            return
        async with security_session_ctx() as s:
            await _run(s)
    except Exception as exc:
        logger.warning("rate_limit: reset_key DB error for key=%r: %s", key, exc)


async def cleanup_expired() -> int:
    """
    Hard-delete all expired rate limit rows across all keys.
    Schedule via TaskManager every 5 minutes to keep the table lean.

    Returns the number of rows deleted.

    Wire it up in your scheduler like:
        task_manager.add_recurring(
            cleanup_expired,
            interval_seconds=300,
            name="rate_limit_cleanup",
        )
    """
    try:
        async with security_session_ctx() as s:
            result = await s.execute(_CLEANUP_ALL_EXPIRED_SQL)
            await s.commit()
            deleted = result.rowcount
            if deleted:
                logger.info("rate_limit cleanup: removed %d expired rows", deleted)
            return deleted
    except Exception as exc:
        logger.warning("rate_limit: cleanup_expired DB error: %s", exc)
        return 0
