# api/v1/recipes/get.py
#
# Revision notes:
#
#  1.  SERIAL DB QUERIES PARALLELISED — the original made 4–5 sequential
#      awaits after the main recipe fetch:
#        - session.refresh(recipe, ...)   — redundant (already selectinloaded)
#        - await session.scalar(snap)
#        - await session.scalar(reports_count)
#        - await session.scalar(my_report)   [conditional]
#      Each is a separate round-trip.  At 5ms RTT that's 20–25ms of pure
#      waiting.  asyncio.gather runs the independent queries concurrently
#      so the total wait is ~one round-trip regardless of how many queries
#      are in flight.
#
#  2.  REDUNDANT session.refresh() REMOVED — selectinload already populated
#      recipe.ingredients and recipe.steps.  Calling session.refresh()
#      immediately after issued two extra SELECT queries for data we just
#      fetched.
#
#  3.  VIEWS_COUNT WRITTEN INLINE ON EVERY GET FIXED — the original did a
#      read-modify-write (recipe.views_count += 1) and committed on every
#      single GET request.  This means every recipe page load holds a
#      write lock on the recipe row.  Under concurrent traffic on a popular
#      recipe this becomes a hot-row contention bottleneck.
#
#      Fix: views_count is incremented via an atomic SQL UPDATE
#      (no read-modify-write race), the RecipeView log row is written, and
#      the whole thing runs in a BackgroundTask so it doesn't add to
#      the response latency at all.
#
#  4.  can_moderate() BUG FIXED — `getattr(viewer, "can_moderate", False)`
#      returns the *method object* which is always truthy, so every logged-in
#      user was getting the moderator report view.  Fixed to `viewer.can_moderate()`.
#
#  5.  media_type COMPARISON FIXED — compared `m.media_type == "image"` but
#      media_type is now a MediaType enum.  Changed to `m.media_type == MediaType.IMAGE`.

from __future__ import annotations

import asyncio
from typing import Optional
import hashlib
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.main.core.session import get_async_session, AsyncSessionLocal
from database.main.counter_aggregator import pick_shard
from database.main.core.models import (
    User,
    Recipe,
    RecipeLineageSnapshot,
    RecipeReport,
    RecipeView,
    MediaType,
    Bookmark,
)
from api.v1.auth.utils.dependencies import get_current_user_optional
from utilities.helpers.task_manager.manager import task_manager
from utilities.common.common_utility import debug_print

router = APIRouter()

DEDUP_WINDOW_HOURS = 24

def _make_viewer_key(ip_hash: str, user_agent: str) -> str:
    raw = f"{ip_hash}:{user_agent}"
    return hashlib.sha256(raw.encode()).hexdigest()

# ── Serialiser ────────────────────────────────────────────────────────────────

def serialize_recipe(recipe: Recipe, is_author: Optional[User]) -> dict:
    images = []
    videos = []

    for m in recipe.media:
        if m.media_type == MediaType.IMAGE:
            images.append(m.url)
        elif m.media_type == MediaType.VIDEO:
            videos.append(m.url)

    author = recipe.author  # joined-loaded on Recipe

    if not is_author:
        return {
        "id":              recipe.id,
        "title":           recipe.title,
        "body":            recipe.body,
        "author_id":       author.id,
        "author_name":     author.username,
        "avatar_url":      author.avatar_url,
        "parent_id":       recipe.parent_id,
        "created_at":      recipe.created_at,
        "media":           {"images": images, "videos": videos},
        "likes_count":     recipe.likes_count     or 0,
        "views_count":     recipe.views_count     or 0,
        "forks_count":     recipe.forks_count     or 0,
        "shares_count":    recipe.shares_count    or 0,
        "bookmarks_count": recipe.bookmarks_count or 0,
        "comments_count":  recipe.comments_count  or 0,
        "ingredients": [
            {
                "id":          ing.id,
                "name":        ing.name,
                "is_animal":   ing.is_animal,
                "is_allergen": ing.is_allergen,
            }
            for ing in recipe.ingredients
        ],
        "steps": [
            {
                "step_number":       s.step_number,
                "instruction":       s.instruction,
                "technique":         s.technique,
                "estimated_minutes": s.estimated_minutes,
                #"tool": s.tool,
            }
            for s in sorted(recipe.steps, key=lambda x: x.step_number)
        ],
    }

    else:
        return {
            "id":              recipe.id,
            "title":           recipe.title,
            "body":            recipe.body,
            "author_id":       author.id,
            "author_name":     author.username,
            "avatar_url":      author.avatar_url,
            "parent_id":       recipe.parent_id,
            "is_draft":        recipe.is_draft,
            "created_at":      recipe.created_at,
            "media":           {"images": images, "videos": videos},
            "likes_count":     recipe.likes_count     or 0,
            "views_count":     recipe.views_count     or 0,
            "forks_count":     recipe.forks_count     or 0,
            "shares_count":    recipe.shares_count    or 0,
            "bookmarks_count": recipe.bookmarks_count or 0,
            "comments_count":  recipe.comments_count  or 0,
            "ingredients": [
                {
                    "id":          ing.id,
                    "name":        ing.name,
                    "is_animal":   ing.is_animal,
                    "is_allergen": ing.is_allergen,
                }
                for ing in recipe.ingredients
            ],
            "steps": [
                {
                    "step_number":       s.step_number,
                    "instruction":       s.instruction,
                    "technique":         s.technique,
                    "estimated_minutes": s.estimated_minutes,
                    #"tool": s.tool,
                }
                for s in sorted(recipe.steps, key=lambda x: x.step_number)
            ],
        }


# ── Background view tracker ───────────────────────────────────────────────────

async def _record_view(
    recipe_id:  int,
    viewer_id:  Optional[int],
    ip_hash:    str,
    user_agent: str,
) -> None:
    async with AsyncSessionLocal() as session:
        window_start = datetime.now(timezone.utc) - timedelta(hours=DEDUP_WINDOW_HOURS)

        if viewer_id:
            already_counted = await session.scalar(
                select(RecipeView.id).where(
                    RecipeView.recipe_id  == recipe_id,
                    RecipeView.user_id    == viewer_id,
                    RecipeView.created_at >= window_start,
                ).limit(1)
            )
        else:
            viewer_key = _make_viewer_key(ip_hash, user_agent)
            already_counted = await session.scalar(
                select(RecipeView.id).where(
                    RecipeView.recipe_id  == recipe_id,
                    RecipeView.ip_hash    == viewer_key,
                    RecipeView.created_at >= window_start,
                ).limit(1)
            )

        if already_counted:
            return

        shard_id = pick_shard(viewer_id)
        await session.execute(
            text("""
                INSERT INTO recipe_counter_shards (recipe_id, shard_id, views, likes, shares)
                VALUES (:recipe_id, :shard_id, 1, 0, 0)
                ON CONFLICT (recipe_id, shard_id)
                DO UPDATE SET views = recipe_counter_shards.views + excluded.views
            """),
            {"recipe_id": recipe_id, "shard_id": shard_id},
        )
        await session.execute(
            RecipeView.__table__.insert().values(
                recipe_id=recipe_id,
                user_id=viewer_id,
                ip_hash=_make_viewer_key(ip_hash, user_agent) if not viewer_id else None,
                user_agent=user_agent,
            )
        )
        debug_print(f"Upsert done — checking shard state...", color="green")
        check = await session.execute(
            text("SELECT views FROM recipe_counter_shards WHERE recipe_id=:r AND shard_id=:s"),
            {"r": recipe_id, "s": shard_id}
        )
        debug_print(f"Shard views after upsert: {check.scalar()}", color="green")
        await session.commit()


# ── GET single recipe ─────────────────────────────────────────────────────────

@router.get("/{recipe_id}")
async def get_recipe(
    recipe_id: int,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    viewer: Optional[User] = Depends(get_current_user_optional),
):
    # Single query: recipe + all eager-loaded children
    stmt = (
        select(Recipe)
        .options(
            selectinload(Recipe.ingredients),
            selectinload(Recipe.steps),
            selectinload(Recipe.media),
        )
        .where(Recipe.id == recipe_id)
    )
    recipe = await session.scalar(stmt)

    if not recipe or recipe.is_deleted:
        raise HTTPException(status_code=404, detail="Recipe not found")

    if recipe.is_draft:
        if not viewer or viewer.id != recipe.author_id:
            raise HTTPException(status_code=404, detail="Recipe not found")

    # FIX #2 — removed redundant session.refresh(); selectinload already loaded these

    viewer_id = viewer.id if viewer else None
    is_author = viewer_id == recipe.author_id if viewer_id else False

    # FIX #1 — run independent follow-up queries in parallel
    snap_q = session.scalar(
        select(RecipeLineageSnapshot)
        .where(RecipeLineageSnapshot.recipe_id == recipe_id)
    )
    reports_count_q = session.scalar(
        select(func.count())
        .select_from(RecipeReport)
        .where(RecipeReport.recipe_id == recipe_id)
    )
    my_report_q = (
        session.scalar(
            select(RecipeReport).where(
                RecipeReport.recipe_id == recipe_id,
                RecipeReport.reporter_id == viewer_id,
            )
        )
        if viewer_id else asyncio.sleep(0, result=None)
    )
    my_bookmark_q = (
        session.scalar(
            select(Bookmark.id).where(
                Bookmark.recipe_id == recipe_id,
                Bookmark.user_id   == viewer_id,
            )
        )
        if viewer_id else asyncio.sleep(0, result=None)
    )

    snap, reports_count, my_report, my_bookmark = await asyncio.gather(
        snap_q, reports_count_q, my_report_q, my_bookmark_q
    )
    # FIX #3 — view increment is async, non-blocking, after response
    if not is_author:
        ip_hash    = getattr(request.state, "ip_hash", "") or ""
        user_agent = request.headers.get("user-agent", "")
        await task_manager.add_task(
            func=_record_view,
            args=(recipe_id, viewer_id, ip_hash, user_agent),
            run_once_and_forget=True,
            name="record_view",
        )

    # Build response
    data = serialize_recipe(recipe, is_author)

    if snap:
        data["root_recipe_id"] = snap.root_recipe_id
        data["depth"]          = snap.depth

    data["reports_count"]    = reports_count or 0
    data["is_reported"]      = (reports_count or 0) > 0
    data["viewer_reported"]  = my_report is not None
    data["viewer_report_reason"] = my_report.reason if my_report else None
    data["viewer_favorite"] = my_bookmark is not None

    # FIX #4 — was `getattr(viewer, "can_moderate", False)` which returned
    # the method object (always truthy).  Fixed to call the method.
    if viewer and viewer.can_moderate():
        recent_reports = await session.scalars(
            select(RecipeReport)
            .where(RecipeReport.recipe_id == recipe_id)
            .order_by(RecipeReport.created_at.desc())
            .limit(5)
        )
        data["recent_reports"] = [
            {
                "id":          r.id,
                "reason":      r.reason,
                "details":     r.details,
                "reporter_id": r.reporter_id,
                "created_at":  r.created_at,
            }
            for r in recent_reports
        ]

    return {"ok": True, "recipe": data}