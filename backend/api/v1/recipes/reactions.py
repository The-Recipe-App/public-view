# api/v1/recipes/reactions.py
#
# Revision notes:
#
#  1.  RACE CONDITION ON ALL COUNTER UPDATES FIXED — every counter increment
#      in the original used Python read-modify-write:
#          recipe.likes_count = (recipe.likes_count or 0) + 1
#      Two concurrent requests read the same value (e.g. 42), both write 43,
#      and one increment is silently lost.  Under any real traffic on a
#      popular recipe this causes consistent undercounting.
#
#      Fix: all counter changes use atomic SQL UPDATE:
#          UPDATE recipes SET likes_count = likes_count + 1 WHERE id = :id
#      The DB handles the increment atomically — no read, no race.
#
#  2.  ACTIVITY WRITES MOVED TO BackgroundTasks — vote, bookmark, and share
#      all wrote Activity rows inside the main transaction.  The user waits
#      for the activity insert before getting a response.  Activity is a
#      fire-and-forget audit log; moved to background tasks.
#
#  3.  ShareableLink.uses COUNTER ALSO ATOMICISED — was read-modify-write
#      like the others.
#
#  4.  track_view INLINE views_count REMOVED — the dedicated track_view
#      endpoint also did a read-modify-write on views_count inline.
#      Now uses the same atomic UPDATE pattern and a proper RecipeView
#      log row.

from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.main.core.session import get_async_session, AsyncSessionLocal
from database.main.counter_aggregator import pick_shard
from database.main.core.models import (
    User,
    Recipe,
    Comment,
    Vote,
    TargetType,
    Bookmark,
    Share,
    ShareableLink,
    RecipeView,
    Activity,
    RecipeCounterShard,
)
from api.v1.auth.utils.dependencies import get_current_user
from api.v1.recipes.schemas import VoteReq, ShareCreateReq

router = APIRouter()


# ── Background activity writer ────────────────────────────────────────────────


async def _write_activity(
    user_id: int,
    verb: str,
    subject_table: str,
    subject_id: int,
    payload: Optional[dict] = None,
) -> None:
    """FIX #2 — fire-and-forget, runs after response is sent."""
    async with AsyncSessionLocal() as session:
        session.add(
            Activity(
                user_id=user_id,
                verb=verb,
                subject_table=subject_table,
                subject_id=subject_id,
                payload=payload,
            )
        )
        await session.commit()


# ── Vote helper ───────────────────────────────────────────────────────────────


async def apply_vote(
    session: AsyncSession,
    user: User,
    target_type: TargetType,
    target_id: int,
    value: int,
) -> dict:
    if value not in (1, -1):
        raise HTTPException(status_code=400, detail="Vote must be +1 or -1")

    Vote.check_can_vote(user)

    existing = await session.scalar(
        select(Vote).where(
            Vote.user_id == user.id,
            Vote.target_type == target_type,
            Vote.target_id == target_id,
        )
    )

    if existing:
        if existing.value == value:
            return {"ok": True, "applied": False}
        old_value = existing.value
        existing.value = value
        session.add(existing)
        # Net delta: new minus old (e.g. flip +1→-1 means delta = -2)
        delta = value - old_value
    else:
        session.add(
            Vote(
                user_id=user.id,
                target_type=target_type,
                target_id=target_id,
                value=value,
            )
        )
        delta = value

    # FIX #1 — atomic SQL increment, no read-modify-write
    if target_type == TargetType.RECIPE:
        recipe_exists = await session.scalar(
            select(Recipe.id).where(Recipe.id == target_id)
        )
        if not recipe_exists:
            raise HTTPException(status_code=404, detail="Recipe not found")

        shard_id = pick_shard(user.id)
        await session.execute(
            update(RecipeCounterShard)
            .where(
                RecipeCounterShard.recipe_id == target_id,
                RecipeCounterShard.shard_id == shard_id,
            )
            .values(likes=RecipeCounterShard.likes + delta)
        )

    elif target_type == TargetType.COMMENT:
        result = await session.execute(
            update(Comment)
            .where(Comment.id == target_id)
            .values(likes_count=Comment.likes_count + delta)
            .returning(Comment.id)
        )
        if not result.fetchone():
            raise HTTPException(status_code=404, detail="Comment not found")

    return {"ok": True, "applied": True}


# ── Vote recipe ───────────────────────────────────────────────────────────────


@router.post("/{recipe_id}/vote")
async def vote_recipe(
    recipe_id: int,
    payload: VoteReq,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    result = await apply_vote(
        session, user, TargetType.RECIPE, recipe_id, int(payload.value)
    )
    await session.commit()

    if result["applied"]:
        background_tasks.add_task(
            _write_activity,
            user.id,
            "vote.recipe",
            "recipes",
            recipe_id,
            {"value": payload.value},
        )

    return result


# ── Vote comment ──────────────────────────────────────────────────────────────


@router.post("/comments/{comment_id}/vote")
async def vote_comment(
    comment_id: int,
    payload: VoteReq,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    result = await apply_vote(
        session, user, TargetType.COMMENT, comment_id, int(payload.value)
    )
    await session.commit()

    if result["applied"]:
        background_tasks.add_task(
            _write_activity,
            user.id,
            "vote.comment",
            "comments",
            comment_id,
            {"value": payload.value},
        )

    return result


# ── Bookmark toggle ───────────────────────────────────────────────────────────


@router.post("/{recipe_id}/favorite")
async def toggle_favorite(
    recipe_id: int,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    recipe_exists = await session.scalar(select(Recipe.id).where(Recipe.id == recipe_id))
    if not recipe_exists:
        raise HTTPException(status_code=404, detail="Recipe not found")

    existing = await session.scalar(
        select(Bookmark).where(
            Bookmark.user_id == user.id,
            Bookmark.recipe_id == recipe_id,
        )
    )

    if existing:
        await session.delete(existing)
        await session.execute(
            update(Recipe)
            .where(Recipe.id == recipe_id)
            .values(bookmarks_count=Recipe.bookmarks_count - 1)
        )
        bookmarked = False
    else:
        session.add(Bookmark(user_id=user.id, recipe_id=recipe_id))
        await session.execute(
            update(Recipe)
            .where(Recipe.id == recipe_id)
            .values(bookmarks_count=Recipe.bookmarks_count + 1)
        )
        bookmarked = True

    await session.commit()

    background_tasks.add_task(
        _write_activity,
        user.id,
        "recipe.bookmark" if bookmarked else "recipe.unbookmark",
        "recipes",
        recipe_id,
    )

    return {"ok": True, "added": bookmarked}


# ── Share recipe ──────────────────────────────────────────────────────────────


@router.post("/{recipe_id}/share", status_code=201)
async def share_recipe(
    recipe_id: int,
    payload: ShareCreateReq,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    recipe_exists = await session.scalar(
        select(Recipe.id).where(Recipe.id == recipe_id)
    )
    if not recipe_exists:
        raise HTTPException(status_code=404, detail="Recipe not found")

    share = Share(
        user_id=user.id,
        recipe_id=recipe_id,
        via=payload.via,
        share_link_id=None,
    )

    if payload.share_link_token:
        link = await session.scalar(
            select(ShareableLink).where(
                ShareableLink.recipe_id == recipe_id,
                ShareableLink.token == payload.share_link_token,
            )
        )
        if link:
            if not link.is_valid:
                raise HTTPException(
                    status_code=410, detail="Share link is expired or exhausted"
                )
            share.share_link_id = link.id
            # FIX #3 — atomic increment on uses
            await session.execute(
                update(ShareableLink)
                .where(ShareableLink.id == link.id)
                .values(uses=ShareableLink.uses + 1)
            )

    session.add(share)

    # FIX #1 — atomic shares_count increment
    shard_id = pick_shard(user.id)
    await session.execute(
        update(RecipeCounterShard)
        .where(
            RecipeCounterShard.recipe_id == recipe_id,
            RecipeCounterShard.shard_id == shard_id,
        )
        .values(shares=RecipeCounterShard.shares + 1)
    )

    await session.commit()
    await session.refresh(share)

    background_tasks.add_task(
        _write_activity,
        user.id,
        "recipe.share",
        "recipes",
        recipe_id,
        {"via": payload.via},
    )

    return {"ok": True, "share_id": share.id}


# ── Track view ────────────────────────────────────────────────────────────────


@router.post("/{recipe_id}/track_view")
async def track_view(
    recipe_id: int,
    session: AsyncSession = Depends(get_async_session),
):
    recipe_exists = await session.scalar(
        select(Recipe.id).where(Recipe.id == recipe_id)
    )
    if not recipe_exists:
        raise HTTPException(status_code=404, detail="Recipe not found")

    # FIX #4 — atomic increment + proper view log row
    shard_id = pick_shard(None)  # anonymous endpoint, no user context

    session.execute(
        update(RecipeCounterShard)
        .where(
            RecipeCounterShard.recipe_id == recipe_id,
            RecipeCounterShard.shard_id == shard_id,
        )
        .values(views=RecipeCounterShard.views + 1)
    ),
    session.execute(RecipeView.__table__.insert().values(recipe_id=recipe_id)),

    await session.commit()
    return {"ok": True}
