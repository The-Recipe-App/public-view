"""
api/v1/search/services/search_service.py
"""

from __future__ import annotations

import hashlib
import asyncio
from threading import RLock
import functools

from fastapi import Request

from cachetools import TTLCache
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.search.services.embed import build_recipe_text, embed_text
from utilities.common.common_utility import debug_print

_cache: TTLCache = TTLCache(maxsize=500, ttl=300)
_cache_lock = RLock()

def _cache_key(query: str, cuisine: str | None = None) -> str:
    normalized = query.strip().lower()
    cuisine_part = (cuisine or "").strip().lower()
    return hashlib.md5(f"{normalized}|{cuisine_part}".encode()).hexdigest()


async def embed_and_save(
    recipe_id: int,
    title: str,
    db: AsyncSession,
    body: str | None = None,
    cuisine: str | None = None,
    ingredient_names: list[str] | None = None,
    request: Request | None = None,
    app = None,
) -> None:
    recipe_text = build_recipe_text(
        title=title,
        body=body,
        ingredient_names=ingredient_names,
    )

    # embed_text is synchronous — run in thread so we don't block the event loop
    loop = asyncio.get_running_loop()
    resolved_app = app if app else request.app

    vector = await loop.run_in_executor(
        None,
        functools.partial(embed_text, recipe_text, app=resolved_app)
    )

    await db.execute(
        text("UPDATE recipes SET embedding = :vec WHERE id = :id"),
        {"vec": str(vector), "id": recipe_id},
    )
    await db.commit()
    debug_print(f"Embedding saved for recipe {recipe_id}", tag="INFO", color="green")


async def hybrid_search(
    query: str,
    db: AsyncSession,
    limit: int = 20,
    semantic_weight: float = 0.7,
    keyword_weight: float = 0.3,
    cuisine: str | None = None,
    request: Request | None = None,
) -> list[dict]:
    key = _cache_key(query, cuisine)

    with _cache_lock:
        if key in _cache:
            debug_print(f"Cache hit for query: {query!r} cuisine: {cuisine!r}", tag="INFO", color="green")
            return _cache[key]

    debug_print(f"Cache miss, searching: {query!r} cuisine: {cuisine!r}", tag="INFO", color="yellow")

    query_vector = embed_text(query, request=request)

    cuisine_filter = ""
    if cuisine:
        cuisine_filter = "AND LOWER(r.cuisine) = LOWER(:cuisine)"

    sql = text(f"""
        WITH semantic AS (
            SELECT
                id,
                1 - (embedding <=> CAST(:vec AS vector)) AS sem_score
            FROM recipes
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:vec AS vector)
            LIMIT 50
        ),
        keyword AS (
            SELECT
                id,
                ts_rank_cd(search_vector, query, 32) AS kw_score
            FROM recipes,
                plainto_tsquery('english', :q) AS query
            WHERE search_vector @@ query
        )
        SELECT
            r.id,
            r.title,
            r.body,
            r.cuisine,
            r.difficulty,
            r.prep_time_mins,
            r.cook_time_mins,
            r.likes_count,
            r.views_count,
            r.score,
            COALESCE(s.sem_score, 0) * :sem_w
                + COALESCE(k.kw_score, 0) * :kw_w AS search_score
        FROM recipes r
        LEFT JOIN semantic s ON r.id = s.id
        LEFT JOIN keyword  k ON r.id = k.id
        WHERE (s.id IS NOT NULL OR k.id IS NOT NULL)
        AND r.is_draft = false
        AND r.is_deleted = false
        {cuisine_filter}
        ORDER BY search_score DESC
        LIMIT :limit
    """)

    params = {
        "vec": str(query_vector),
        "q": query,
        "sem_w": semantic_weight,
        "kw_w": keyword_weight,
        "limit": limit,
    }
    if cuisine:
        params["cuisine"] = cuisine

    result = await db.execute(sql, params)

    rows = [dict(row) for row in result.mappings()]

    with _cache_lock:
        _cache[key] = rows

    return rows


def invalidate_cache() -> None:
    with _cache_lock:
        _cache.clear()
    debug_print("Search cache cleared.", tag="INFO", color="yellow")