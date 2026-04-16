# api/v1/notifications/notifications.py
from __future__ import annotations
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.main.core.session import get_async_session
from database.main.core.models import Activity, User, Recipe
from api.v1.auth.utils.dependencies import get_current_user
from sqlalchemy.orm import selectinload

router = APIRouter(prefix="/notifications", tags=["notifications"])

VERB_LABELS = {
    "vote.recipe":      "liked your recipe",
    "recipe.bookmark":  "bookmarked your recipe",
    "comment.create":   "commented on your recipe",
    "recipe.fork":      "forked your recipe",
}

@router.get("")
async def get_notifications(
    limit: int = Query(default=20, le=50),
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    # Get activities on recipes owned by current user
    # but NOT by the user themselves
    owned_recipes = await session.scalars(
        select(Recipe.id).where(Recipe.author_id == user.id)
    )
    recipe_ids = list(owned_recipes)

    if not recipe_ids:
        return {"notifications": [], "unread_count": 0}

    rows = await session.scalars(
        select(Activity)
        .options(selectinload(Activity.user))
        .where(
            Activity.subject_table == "recipes",
            Activity.subject_id.in_(recipe_ids),
            Activity.verb.in_(VERB_LABELS.keys()),
            Activity.user_id != user.id,
        )
        .order_by(Activity.created_at.desc())
        .limit(limit)
    )
    activities = list(rows)

    return {
        "notifications": [
            {
                "id":         a.id,
                "verb":       a.verb,
                "label":      VERB_LABELS.get(a.verb, a.verb),
                "actor":      a.user.username if a.user else "Someone",
                "recipe_id":  a.subject_id,
                "created_at": a.created_at,
            }
            for a in activities
        ],
        "unread_count": len(activities),
    }