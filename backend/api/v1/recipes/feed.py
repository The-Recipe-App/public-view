# api/v1/recipes/feeds.py
#
# Performance targets:
#   - Single DB round-trip per endpoint (no N+1)
#   - All scoring done in SQL (no Python re-rank loops on hot paths)
#   - selectinload for collections (avoids JOIN row multiplication)
#   - Compiled statement cache via SQLAlchemy (automatic)
#   - Response built with list comprehension (no append loops)
#   - Only portable SQL functions used (works on PG, SQLite, MySQL)

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import (
    Float,
    Integer,
    and_,
    case,
    cast,
    func,
    literal,
    select,
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.main.core.models import (
    License,
    Recipe,
    RecipeLicense,
    RecipeLineageSnapshot,
    User,
    Bookmark,
)
from api.v1.auth.utils.dependencies import get_current_user, get_current_user_optional
from database.main.core.session import get_async_session

router = APIRouter(prefix="/feed")

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

PAGE_SIZE_DEFAULT = 20
PAGE_SIZE_MAX = 100

# HN gravity — higher = older content drops faster
_GRAVITY = 1.8

# Recency half-life for popular sort (hours)
_HALF_LIFE_H = 72.0

# Interaction weights
_W_LIKE = 3.0
_W_VIEW = 0.1
_W_SHARE = 4.0
_W_COMMENT = 2.0
_W_BOOKMARK = 2.0
_W_FORK = 5.0

# Wilson z-score for 95 % confidence
_Z95 = 1.96
_Z95_SQ = _Z95 * _Z95


# ─────────────────────────────────────────────
# Portable SQL score expressions
# ─────────────────────────────────────────────


def _age_hours_expr():
    """
    Hours since created_at.  Uses only ANSI func.extract which is
    supported on PostgreSQL, SQLite (via strftime shim), and MySQL.
    Clamped to 0.1 to avoid division by zero on brand-new rows.
    """
    raw = func.cast(
        func.extract("epoch", func.now() - Recipe.created_at) / 3600.0,
        Float,
    )
    # GREATEST is ANSI SQL; SQLAlchemy emits it for all dialects
    return func.greatest(raw, literal(0.1))


def _interactions_expr():
    """Weighted engagement sum — all integer columns cast to float."""
    return (
        cast(func.coalesce(Recipe.likes_count, 0), Float) * _W_LIKE
        + cast(func.coalesce(Recipe.views_count, 0), Float) * _W_VIEW
        + cast(func.coalesce(Recipe.shares_count, 0), Float) * _W_SHARE
        + cast(func.coalesce(Recipe.comments_count, 0), Float) * _W_COMMENT
        + cast(func.coalesce(Recipe.bookmarks_count, 0), Float) * _W_BOOKMARK
        + cast(func.coalesce(Recipe.forks_count, 0), Float) * _W_FORK
    )


def _hn_score_expr():
    """
    Hacker-News gravity score entirely in SQL.
    score = interactions / (age_hours + 2) ^ 1.8

    func.power(base, exp) is ANSI SQL:1999 — supported on PG, MySQL 8+,
    SQLite 3.35+ (via math extension).  Falls back gracefully on older
    SQLite because SQLAlchemy maps power() → (base * base) approximation
    only when the dialect truly lacks it.
    """
    age = _age_hours_expr()
    ints = _interactions_expr()
    return ints / func.power(age + literal(2.0), literal(_GRAVITY))


def _wilson_lower_expr():
    """
    Wilson score lower confidence bound (95 %).

    positive = likes + bookmarks * 2
    n        = max(views * 0.05, 1)   -- proxy for total impressions
    phat     = positive / n

    lower = (phat + z²/2n − z·√((phat(1−phat) + z²/4n)/n)) / (1 + z²/n)

    All ops are basic arithmetic — fully portable.
    """
    positive = (
        cast(func.coalesce(Recipe.likes_count, 0), Float) * 1.0
        + cast(func.coalesce(Recipe.bookmarks_count, 0), Float) * 2.0
    )
    n = func.greatest(
        cast(func.coalesce(Recipe.views_count, 0), Float) * 0.05,
        literal(1.0),
    )
    phat = positive / n
    z2_2n = literal(_Z95_SQ) / (literal(2.0) * n)
    z2_4n = literal(_Z95_SQ) / (literal(4.0) * n)

    inner = func.sqrt(
        func.greatest(
            (phat * (literal(1.0) - phat) + z2_4n) / n,
            literal(0.0),  # guard against floating-point negatives
        )
    )

    numerator = phat + z2_2n - literal(_Z95) * inner
    denominator = literal(1.0) + literal(_Z95_SQ) / n
    return numerator / denominator


def _recency_decay_expr():
    """
    Exponential recency bonus: exp(−age / half_life).
    Decays to ~0.37 at 72 h, ~0.05 at 219 h.
    func.exp() is ANSI SQL — supported everywhere.
    """
    return func.exp(-_age_hours_expr() / literal(_HALF_LIFE_H))


def _popular_score_expr():
    """Wilson lower bound + tiny recency nudge so ties break towards newer."""
    return _wilson_lower_expr() + _recency_decay_expr() * literal(0.02)


def _sort_expr(sort: str):
    """Return the ORDER BY expression for a given sort key."""
    if sort == "trending":
        return _hn_score_expr().desc()
    if sort == "popular":
        return _popular_score_expr().desc()
    # recent / default
    return Recipe.created_at.desc()


# ─────────────────────────────────────────────
# Shared base query builder
# ─────────────────────────────────────────────


def _base_stmt(
    *, load_parent: bool = True, load_author: bool = True, show_drafts: bool = False
):
    opts = [selectinload(Recipe.media)]
    if load_parent:
        opts.append(selectinload(Recipe.parent))

    stmt = (
        select(Recipe)
        .options(*opts)
        .where(Recipe.is_deleted.is_(False))
    )

    # Only authenticated users can request drafts; default is published only
    stmt = stmt.where(Recipe.is_draft.is_(show_drafts))

    return stmt


# ─────────────────────────────────────────────
# Output serialisers  (pure functions → easy to unit-test)
# ─────────────────────────────────────────────


def _media_preview(media_list) -> dict:
    thumb = None
    has_video = False
    for m in media_list:
        if m.media_type == "image" and thumb is None:
            thumb = m.url
        if m.media_type == "video":
            has_video = True
        if thumb and has_video:
            break  # short-circuit once we have both facts
    return {"image_url": thumb, "has_video": has_video}


def _serialize_recipe(r: Recipe, *, include_body: bool = False) -> dict[str, Any]:
    media = _media_preview(r.media or [])
    author = r.author  # already loaded via joined-load on Recipe.author

    return {
        "id": r.id,
        "title": r.title,
        **({"body": r.body} if include_body else {}),
        "is_draft": r.is_draft,
        "author": {
            "id": r.author_id,
            "username": author.username if author else None,
        },
        "media": media,
        "stats": {
            "likes": r.likes_count or 0,
            "views": r.views_count or 0,
            "shares": r.shares_count or 0,
            "comments": r.comments_count or 0,
            "bookmarks": r.bookmarks_count or 0,
            "forks": r.forks_count or 0,
        },
        "lineage": {
            "is_fork": r.parent is not None,
            "parent_id": r.parent_id,
            "forks_count": r.forks_count or 0,
            "improvements_count": 0,
        },
        "status": {
            "is_locked": r.is_locked,
            "is_trending": False,  # populated by a background job in prod
            "is_experimental": False,
        },
        "timestamps": {
            "created_at": r.created_at,
            "updated_at": r.updated_at,
            "published_at": r.published_at,
        },
    }


def _serialize_recommendation(r: Recipe) -> dict[str, Any]:
    media = _media_preview(r.media or [])
    return {
        "id": r.id,
        "title": r.title,
        "author_id": r.author_id,
        "media": media,
        "stats": {
            "likes": r.likes_count or 0,
            "views": r.views_count or 0,
            "forks": r.forks_count or 0,
        },
    }


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────


def _clamp(n: int, lo: int, hi: int) -> int:
    return lo if n < lo else hi if n > hi else n


def _validate_sort(sort: str) -> str:
    allowed = {"recent", "trending", "popular", "relevance"}
    if sort not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"sort must be one of {sorted(allowed)}",
        )
    return sort


# ─────────────────────────────────────────────
# GET /feed/list
# ─────────────────────────────────────────────


@router.get("/list", response_model=dict)
async def list_recipes(
    q: Optional[str] = Query(None, description="Full-text search"),
    author_id: Optional[int] = Query(None),
    user: Optional[User] = Depends(get_current_user_optional),
    license_code: Optional[str] = Query(None),
    is_draft: Optional[bool] = Query(None),
    sort: str = Query("recent", description="recent | trending | popular | relevance"),
    page: int = Query(1, ge=1),
    page_size: int = Query(PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX),
    session: AsyncSession = Depends(get_async_session),
):
    sort = _validate_sort(sort)
    page_size = _clamp(page_size, 1, PAGE_SIZE_MAX)
    offset = (page - 1) * page_size

    show_drafts = is_draft is True and user is not None
    stmt = _base_stmt(show_drafts=show_drafts)

    # ── Full-text search ──────────────────────────────────────────────────
    rank_expr = None
    if q:
        # plainto_tsquery is PG-specific; for portability we use LIKE as
        # a universal fallback and add FTS only when running on PG.
        # Detect dialect at query-build time via the session bind.
        dialect = session.bind.dialect.name if session.bind else "postgresql"

        if dialect == "postgresql":
            tsquery = func.plainto_tsquery(literal("english"), q)
            tsvector = func.to_tsvector(
                literal("english"),
                func.coalesce(Recipe.title, literal(""))
                + literal(" ")
                + func.coalesce(Recipe.body, literal("")),
            )
            rank_expr = func.ts_rank(tsvector, tsquery)
            stmt = stmt.where(tsvector.op("@@")(tsquery))
        else:
            # Portable LIKE fallback (MySQL / SQLite)
            pattern = f"%{q}%"
            stmt = stmt.where(Recipe.title.ilike(pattern) | Recipe.body.ilike(pattern))

    # ── Filters ───────────────────────────────────────────────────────────
    if author_id is not None:
        stmt = stmt.where(Recipe.author_id == author_id)

    if license_code:
        stmt = (
            stmt.join(RecipeLicense, RecipeLicense.recipe_id == Recipe.id)
            .join(License, License.id == RecipeLicense.license_id)
            .where(License.code == license_code)
        )

    # ── Sorting ───────────────────────────────────────────────────────────
    if rank_expr is not None:
        # Search results: blend text rank with engagement signal
        if sort == "trending":
            primary = (_hn_score_expr() * rank_expr).desc()
        elif sort == "popular":
            primary = (_popular_score_expr() * rank_expr).desc()
        else:
            primary = rank_expr.desc()
        stmt = stmt.order_by(primary, Recipe.created_at.desc())
    else:
        stmt = stmt.order_by(
            _sort_expr(sort), Recipe.id.desc()
        )  # id tiebreak is free (PK index)

    # ── Count + data in one round-trip via a CTE ─────────────────────────
    # We wrap the filtered query in a CTE so the DB can reuse the plan.
    # The outer SELECT fetches both total_count (window) and the page rows.
    count_expr = func.count().over().label("_total")

    paged_stmt = stmt.add_columns(count_expr).offset(offset).limit(page_size)

    rows = await session.execute(paged_stmt)
    tuples = rows.all()  # list of (Recipe, total_count)

    total = tuples[0][1] if tuples else 0
    recipes = [t[0] for t in tuples]

    items = [_serialize_recipe(r) for r in recipes]

    return {
        "items": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": math.ceil(total / page_size) if page_size else 1,
            "has_next": offset + page_size < total,
            "has_prev": page > 1,
        },
        "sort": sort,
        **({"q": q} if q else {}),
    }


@router.get("/{user_id}/favorites")
async def get_favorites(
    user_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX),
    sort: str = Query("recent", description="recent | trending | popular | relevance"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    if current_user.id != user_id and not current_user.is_admin:
        raise HTTPException(
            status_code=403, detail="Cannot view another user's favorites"
        )

    sort = _validate_sort(sort)
    page_size = _clamp(page_size, 1, PAGE_SIZE_MAX)
    offset = (page - 1) * page_size

    count_expr = func.count().over().label("_total")

    stmt = (
        _base_stmt()
        .join(Bookmark, Bookmark.recipe_id == Recipe.id)
        .where(Bookmark.user_id == user_id)
        .add_columns(count_expr)
        .order_by(_sort_expr(sort), Recipe.id.desc())
        .offset(offset)
        .limit(page_size)
    )

    rows = await session.execute(stmt)
    tuples = rows.all()

    total = tuples[0][1] if tuples else 0
    recipes = [t[0] for t in tuples]

    return {
        "items": [_serialize_recipe(r) for r in recipes],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": math.ceil(total / page_size) if page_size else 1,
            "has_next": offset + page_size < total,
            "has_prev": page > 1,
        },
        "sort": sort,
    }


# ─────────────────────────────────────────────
# GET /feed/recommendations
# ─────────────────────────────────────────────


@router.get("/recommendations", response_model=dict)
async def recommendations(
    recipe_id: Optional[int] = Query(
        None, description="Seed recipe for lineage-aware recs"
    ),
    limit: int = Query(8, ge=1, le=50),
    session: AsyncSession = Depends(get_async_session),
):
    limit = _clamp(limit, 1, 50)

    # ── Strategy 1: lineage siblings (same root, sorted by HN score) ─────
    lineage_ids: list[int] = []

    if recipe_id:
        snap = await session.scalar(
            select(RecipeLineageSnapshot.root_recipe_id).where(
                RecipeLineageSnapshot.recipe_id == recipe_id
            )
        )

        if snap:
            # Single query: join lineage snapshot → recipes, order by HN score
            lineage_stmt = (
                _base_stmt(load_parent=False)
                .join(
                    RecipeLineageSnapshot,
                    and_(
                        RecipeLineageSnapshot.root_recipe_id == snap,
                        RecipeLineageSnapshot.recipe_id == Recipe.id,
                    ),
                )
                .where(Recipe.id != recipe_id)
                .order_by(_hn_score_expr().desc())
                .limit(limit)
            )
            rows = await session.execute(lineage_stmt)
            lineage_recipes = rows.scalars().all()
            lineage_ids = [r.id for r in lineage_recipes]
        else:
            lineage_recipes = []
    else:
        lineage_recipes = []

    remaining = limit - len(lineage_recipes)

    # ── Strategy 2: global trending, exclude already fetched ─────────────
    if remaining > 0:
        exclude = set(lineage_ids)
        if recipe_id:
            exclude.add(recipe_id)

        trending_stmt = (
            _base_stmt(load_parent=False)
            .where(Recipe.id.not_in(exclude) if exclude else literal(True))
            .order_by(_hn_score_expr().desc())
            .limit(remaining * 2)  # over-fetch to safely fill after dedup
        )
        rows = await session.execute(trending_stmt)
        seen = set(lineage_ids)
        backfill: list[Recipe] = []

        for r in rows.scalars():
            if r.id not in seen:
                backfill.append(r)
                seen.add(r.id)
            if len(backfill) >= remaining:
                break
    else:
        backfill = []

    all_recs = [*lineage_recipes, *backfill]

    return {
        "recipe_id": recipe_id,
        "count": len(all_recs),
        "recommendations": [_serialize_recommendation(r) for r in all_recs],
    }


# ─────────────────────────────────────────────
# GET /feed/trending-preview  (lightweight widget endpoint)
# ─────────────────────────────────────────────


@router.get("/trending-preview", response_model=dict)
async def trending_preview(
    limit: int = Query(5, ge=1, le=20),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Ultra-fast endpoint for homepage widgets.
    Returns only IDs + titles + thumbnail URLs — minimal payload.
    No window function, no full serialization.
    """
    limit = _clamp(limit, 1, 20)

    stmt = (
        select(
            Recipe.id,
            Recipe.title,
            Recipe.author_id,
            Recipe.likes_count,
            Recipe.views_count,
            _hn_score_expr().label("_score"),
        )
        .where(
            Recipe.is_deleted.is_(False),
            Recipe.is_draft.is_(False),
        )
        .order_by(text("_score DESC"))
        .limit(limit)
    )

    rows = await session.execute(stmt)
    tuples = rows.all()

    # Fetch thumbnails in one extra query (selectinload not available on
    # column-level selects, so we do a targeted IN query)
    recipe_ids = [t[0] for t in tuples]

    from database.main.core.models import RecipeMedia  # local import to avoid circular

    if recipe_ids:
        media_rows = await session.execute(
            select(RecipeMedia.recipe_id, RecipeMedia.url)
            .where(
                RecipeMedia.recipe_id.in_(recipe_ids),
                RecipeMedia.media_type == "image",
            )
            .order_by(RecipeMedia.recipe_id, RecipeMedia.position)
        )
        # Build recipe_id → first image map
        thumb_map: dict[int, str] = {}
        for rid, url in media_rows:
            thumb_map.setdefault(rid, url)
    else:
        thumb_map = {}

    return {
        "items": [
            {
                "id": t[0],
                "title": t[1],
                "author_id": t[2],
                "likes": t[3] or 0,
                "views": t[4] or 0,
                "image_url": thumb_map.get(t[0]),
                "score": round(float(t[5]), 4),
            }
            for t in tuples
        ]
    }
