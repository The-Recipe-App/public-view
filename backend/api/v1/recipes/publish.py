# api/v1/recipes/publish.py

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from database.main.core.session import get_async_session
from database.main.core.models import User, Recipe, Activity
from api.v1.auth.utils.dependencies import get_current_user

router = APIRouter()


# ----------------------------
# ✅ PUBLISH RECIPE
# ----------------------------
@router.post("/{recipe_id}/publish")
async def publish_recipe(
    recipe_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
    request: Request = None,
):
    try:
        recipe = await session.get(Recipe, recipe_id)

        if not recipe or recipe.is_deleted:
            raise HTTPException(status_code=404, detail="Recipe not found")

        if recipe.author_id != user.id:
            raise HTTPException(status_code=403, detail="Not your recipe")

        if recipe.is_locked:
            raise HTTPException(status_code=403, detail="Recipe is locked")

        if not recipe.is_draft:
            return {"ok": True, "published": True}

        recipe.is_draft = False
        recipe.published_at = datetime.now(timezone.utc)
        session.add(recipe)

        session.add(
            Activity(
                user_id=user.id,
                verb="recipe.publish",
                subject_table="recipes",
                subject_id=recipe.id,
                payload=None,
            )
        )

        await session.commit()
        if request.app.state.model_ready.is_set():
            from api.v1.recipes._embedding import _schedule_embedding
            _schedule_embedding(
                request=request,
                recipe_id=recipe.id,
                title=recipe.title,
                body=recipe.body,
                ingredient_names=list(recipe.ingredient_names),
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"ok": True, "published": True}


# ----------------------------
# ✅ UNPUBLISH RECIPE
# ----------------------------
@router.post("/{recipe_id}/unpublish")
async def unpublish_recipe(
    recipe_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    recipe = await session.get(Recipe, recipe_id)

    if not recipe or recipe.is_deleted:
        raise HTTPException(status_code=404, detail="Recipe not found")

    if recipe.author_id != user.id:
        raise HTTPException(status_code=403, detail="Not your recipe")

    if recipe.is_locked:
        raise HTTPException(status_code=403, detail="Recipe is locked")

    recipe.is_draft = True
    recipe.published_at = None
    session.add(recipe)

    session.add(
        Activity(
            user_id=user.id,
            verb="recipe.unpublish",
            subject_table="recipes",
            subject_id=recipe.id,
            payload=None,
        )
    )

    await session.commit()
    return {"ok": True, "published": False}
