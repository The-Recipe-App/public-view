# database/main/counter_aggregator.py
#
# Counter Shard Aggregator
# ========================
#
# WHY THIS EXISTS
# ───────────────
# Every view, like, share, and bookmark currently does a direct UPDATE on the
# recipe row:
#
#     UPDATE recipes SET views_count = views_count + 1 WHERE id = :id
#
# On a low-traffic recipe this is fine. On a hot recipe (front page, going
# viral) hundreds of concurrent requests all fight for the same row lock.
# PostgreSQL serialises them — each writer blocks until the previous one
# commits — and end-to-end latency climbs steeply.
#
# RecipeCounterShard spreads that write contention across N shards. A request
# picks one shard (by hashing its user/session id mod N) and increments that
# shard. No two requests fight unless they hash to the same shard — 8 shards
# means 8× less contention.
#
# This aggregator runs periodically (default: every 60 seconds) and rolls
# all dirty shard increments into the canonical recipe.{views,likes,shares}_count
# columns, then resets the shards to zero.
#
# DESIGN
# ──────
#  - Single CTE per recipe: atomically read + zero shards + update recipe row
#  - Only processes recipes where at least one shard is non-zero (dirty check)
#  - Runs inside a single DB transaction; on failure the shards are untouched
#    and will be picked up on the next cycle
#  - SHARD_COUNT is intentionally small (default 8); too many shards means
#    more rows to scan and lock, which isn't free either
#  - Wire up via TaskManager.add_recurring() in app startup

from __future__ import annotations

import asyncio
import logging
import os
from typing import Sequence

from sqlalchemy import select, update, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.main.core.session import AsyncSessionLocal
from database.main.core.models import Recipe, RecipeCounterShard

from utilities.common.common_utility import debug_print

logger = logging.getLogger("counter_aggregator")

# Number of shards per recipe.  Must match what the write path uses.
SHARD_COUNT: int = int(os.getenv("COUNTER_SHARD_COUNT", "8"))


# ── Shard picker (used by write paths) ───────────────────────────────────────


def pick_shard(user_id: int | None, session_key: str | None = None) -> int:
    """
    Deterministically pick a shard index for a given user/session.
    Uses the user_id when available; falls back to hashing the session key
    or a random shard for anonymous users.

    Call this from get.py, reactions.py, etc. instead of writing directly
    to recipe.views_count / recipe.likes_count.

    Example:
        shard_id = pick_shard(viewer_id)
        await session.execute(
            update(RecipeCounterShard)
            .where(
                RecipeCounterShard.recipe_id == recipe_id,
                RecipeCounterShard.shard_id  == shard_id,
            )
            .values(views=RecipeCounterShard.views + 1)
        )
    """
    if user_id is not None:
        return user_id % SHARD_COUNT
    if session_key:
        return hash(session_key) % SHARD_COUNT
    import random

    return random.randrange(SHARD_COUNT)


async def ensure_shards(session: AsyncSession, recipe_id: int) -> None:
    """
    Create the N shard rows for a recipe if they don't already exist.
    Call this once when a recipe is first created.
    """
    existing = await session.scalars(
        select(RecipeCounterShard.shard_id).where(
            RecipeCounterShard.recipe_id == recipe_id
        )
    )
    existing_ids = set(existing.all())
    missing = [i for i in range(SHARD_COUNT) if i not in existing_ids]

    if missing:
        session.add_all(
            [
                RecipeCounterShard(
                    recipe_id=recipe_id,
                    shard_id=shard_id,
                    views=0,
                    likes=0,
                    shares=0,
                )
                for shard_id in missing
            ]
        )


# ── Aggregation ───────────────────────────────────────────────────────────────


async def aggregate_once() -> int:
    async with AsyncSessionLocal() as session:
        # Force a fresh read — no transaction snapshot from session.begin()
        dirty_result = await session.execute(
            text("""
                SELECT DISTINCT recipe_id 
                FROM recipe_counter_shards 
                WHERE views > 0 OR likes > 0 OR shares > 0
            """)
        )
        dirty_recipe_ids = [row[0] for row in dirty_result.all()]
        
        debug_print(f"Dirty recipe ids: {dirty_recipe_ids}", color="dim")
        
        if not dirty_recipe_ids:
            return 0

        updated = 0
        for recipe_id in dirty_recipe_ids:
            await session.execute(
                text("""
                    WITH
                    snapshot AS (
                        SELECT SUM(views) AS views, SUM(likes) AS likes, SUM(shares) AS shares
                        FROM recipe_counter_shards
                        WHERE recipe_id = :rid
                    ),
                    zeroed AS (
                        UPDATE recipe_counter_shards
                        SET views = 0, likes = 0, shares = 0
                        WHERE recipe_id = :rid
                    )
                    UPDATE recipes
                    SET views_count  = views_count  + (SELECT views  FROM snapshot),
                        likes_count  = likes_count  + (SELECT likes  FROM snapshot),
                        shares_count = shares_count + (SELECT shares FROM snapshot)
                    WHERE id = :rid
                """),
                {"rid": recipe_id},
            )
            updated += 1

        await session.commit()
        debug_print(f"Aggregator flushed {updated} recipe(s)", color="green")
        return updated

async def run_aggregator_loop(interval_seconds: float = 60.0) -> None:
    """
    Standalone loop for use without TaskManager (e.g. in tests or
    if you prefer a separate asyncio.Task).
    """
    while True:
        try:
            n = await aggregate_once()
            if n:
                logger.info("Counter aggregator: flushed %d recipe(s)", n)
        except Exception:
            logger.exception("Counter aggregator error; will retry next cycle")
        await asyncio.sleep(interval_seconds)

