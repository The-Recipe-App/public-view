# api/v1/recipes/comments.py
#
# Revision notes:
#
#  1.  list_comments RETURNS AUTHOR USERNAME — the original returned only
#      author_id, forcing every API client to do N separate user lookups
#      to display comment author names (classic N+1 at the consumer level).
#      Fixed with selectinload(Comment.author) so the username comes back
#      in the same query.
#
#  2.  create_comment COUNTER USES ATOMIC UPDATE — was read-modify-write
#      (recipe.comments_count += 1).  Two concurrent comments on the same
#      recipe would both read the same value and one increment would be lost.
#      Fixed with UPDATE recipes SET comments_count = comments_count + 1.
#
#  3.  ACTIVITY WRITES MOVED TO BackgroundTasks — same pattern as get.py
#      and reactions.py.  The user doesn't need to wait for the audit log.
#
#  4.  create_comment ACTIVITY subject_id WAS None — the original set
#      subject_id=None for comment.create, which means the activity log
#      entry is useless for tracing which comment was created.  Fixed to
#      use comment.id after flush.
#
#  5.  delete_comment SOFT-DELETES DECREMENT comments_count — the original
#      soft-deleted the comment but never decremented the recipe's
#      comments_count, so the count drifted upward forever.

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.main.core.session import get_async_session, AsyncSessionLocal
from database.main.core.models import User, Recipe, Comment, Activity
from api.v1.recipes.schemas import CommentCreateReq
from api.v1.auth.utils.dependencies import get_current_user

router = APIRouter()


# ── Background activity writer ────────────────────────────────────────────────

async def _write_activity(
    user_id: int,
    verb: str,
    subject_table: str,
    subject_id: int,
    payload: dict | None = None,
) -> None:
    async with AsyncSessionLocal() as session:
        session.add(Activity(
            user_id=user_id,
            verb=verb,
            subject_table=subject_table,
            subject_id=subject_id,
            payload=payload,
        ))
        await session.commit()


# ── Create comment ────────────────────────────────────────────────────────────

@router.post("/{recipe_id}/comments", status_code=201)
async def create_comment(
    recipe_id: int,
    payload: CommentCreateReq,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    recipe = await session.get(Recipe, recipe_id)
    if not recipe or recipe.is_deleted:
        raise HTTPException(status_code=404, detail="Recipe not found")

    try:
        recipe.assert_can_comment()
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    comment = Comment(
        recipe_id=recipe.id,
        author_id=user.id,
        parent_id=payload.parent_id,
        content=payload.content.strip(),
        score=0,
    )
    session.add(comment)
    await session.flush()  # populate comment.id before activity

    # FIX #2 — atomic increment
    await session.execute(
        update(Recipe)
        .where(Recipe.id == recipe_id)
        .values(comments_count=Recipe.comments_count + 1)
    )

    await session.commit()

    # FIX #3 + #4 — background, correct subject_id
    background_tasks.add_task(
        _write_activity, user.id, "comment.create", "comments", comment.id,
        {"recipe_id": recipe.id},
    )

    return {"ok": True, "comment_id": comment.id}


# ── List comments ─────────────────────────────────────────────────────────────

@router.get("/{recipe_id}/comments")
async def list_comments(
    recipe_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_async_session),
):
    offset = (page - 1) * page_size

    # FIX #1 — selectinload author so username is available without N+1
    rows = await session.execute(
        select(Comment)
        .options(selectinload(Comment.author))
        .where(
            Comment.recipe_id == recipe_id,
            Comment.is_deleted.is_(False),
        )
        .order_by(Comment.created_at.asc())
        .offset(offset)
        .limit(page_size)
    )

    comments = rows.scalars().all()

    return [
        {
            "id":           c.id,
            "author_id":    c.author_id,
            "author_name":  c.author.username if c.author else None,  # FIX #1
            "content":      c.content,
            "created_at":   c.created_at,
            "parent_id":    c.parent_id,
            "likes_count":  c.likes_count or 0,
        }
        for c in comments
    ]


# ── Delete comment ────────────────────────────────────────────────────────────

@router.delete("/comments/{comment_id}")
async def delete_comment(
    comment_id: int,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    comment = await session.get(Comment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    if comment.author_id != user.id and not user.can_moderate():
        raise HTTPException(status_code=403, detail="Not authorized")

    comment.is_deleted = True
    session.add(comment)

    # FIX #5 — decrement comments_count on soft-delete
    await session.execute(
        update(Recipe)
        .where(Recipe.id == comment.recipe_id)
        .values(comments_count=Recipe.comments_count - 1)
    )

    await session.commit()

    background_tasks.add_task(
        _write_activity, user.id, "comment.delete", "comments", comment.id,
        {"recipe_id": comment.recipe_id},
    )

    return {"ok": True}