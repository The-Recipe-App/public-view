# api/v1/recipes/edit.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert

from database.main.core.session import get_async_session
from database.main.core.models import (
    User,
    Recipe,
    Ingredient,
    RecipeStep,
    Activity,

    # ✅ NEW
    RecipeMedia,
)

from api.v1.auth.utils.dependencies import get_current_user
from api.v1.recipes.schemas import EditRecipeReq

router = APIRouter()


# ============================================================
# ✅ MEDIA VALIDATION HELPER
# ============================================================

def _split_media(media_items):
    """
    Splits incoming media into images/videos and validates type.
    """
    images = []
    videos = []

    for m in media_items:
        if m.media_type == "image":
            images.append(m)
        elif m.media_type == "video":
            videos.append(m)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid media_type: {m.media_type}",
            )

    return images, videos


# ============================================================
# ✅ EDIT RECIPE
# PATCH /recipes/{id}
# ============================================================

@router.patch("/{recipe_id}")
async def edit_recipe(
    recipe_id: int,
    payload: EditRecipeReq,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    recipe = await session.get(Recipe, recipe_id)

    if not recipe or recipe.is_deleted:
        raise HTTPException(status_code=404, detail="Recipe not found")

    # Only author can edit
    if recipe.author_id != user.id:
        raise HTTPException(status_code=403, detail="Not your recipe")

    # Locked recipes cannot be edited
    if recipe.is_locked:
        raise HTTPException(status_code=403, detail="Recipe is locked")

    # ----------------------------
    # Update title/body
    # ----------------------------
    if payload.title is not None:
        recipe.title = payload.title.strip()

    if payload.body is not None:
        recipe.body = payload.body

    # ----------------------------
    # Replace Ingredients (FAST)
    # ----------------------------
    if payload.ingredients is not None:
        # Bulk delete old
        await session.execute(
            delete(Ingredient).where(
                Ingredient.recipe_id == recipe.id
            )
        )

        # Bulk insert new
        if payload.ingredients:
            session.add_all(
                [
                    Ingredient(
                        recipe_id=recipe.id,
                        name=ing.name.strip(),
                        is_animal=ing.is_animal,
                        is_allergen=ing.is_allergen,
                    )
                    for ing in payload.ingredients
                ]
            )

    # ----------------------------
    # Replace Steps (FAST)
    # ----------------------------
    if payload.steps is not None:
        await session.execute(
            delete(RecipeStep).where(
                RecipeStep.recipe_id == recipe.id
            )
        )

        if payload.steps:
            session.add_all(
                [
                    RecipeStep(
                        recipe_id=recipe.id,
                        step_number=s.step_number,
                        instruction=s.instruction.strip(),
                        technique=s.technique,
                        estimated_minutes=s.estimated_minutes or 0,
                    )
                    for s in sorted(payload.steps, key=lambda x: x.step_number)
                ]
            )

    # ----------------------------
    # ✅ Replace Media (Tier Limited)
    # ----------------------------
    if payload.media is not None:

        images, videos = _split_media(payload.media)

        # Plan enforcement
        if videos and not user.plan_allows_videos():
            raise HTTPException(
                status_code=403,
                detail="Your plan does not allow video uploads",
            )

        # Limits enforcement
        if len(images) > user.allowed_images_limit():
            raise HTTPException(
                status_code=400,
                detail="Too many images for your plan tier",
            )

        if videos and len(videos) > user.allowed_videos_limit():
            raise HTTPException(
                status_code=400,
                detail="Too many videos for your plan tier",
            )

        # Bulk delete old media
        await session.execute(
            delete(RecipeMedia).where(
                RecipeMedia.recipe_id == recipe.id
            )
        )

        # Bulk insert new media (FAST)
        if payload.media:
            rows = [
                {
                    "recipe_id": recipe.id,
                    "media_type": m.media_type,
                    "url": m.url,
                    "position": m.position or 0,
                }
                for m in sorted(payload.media, key=lambda x: x.position)
            ]

            await session.execute(
                insert(RecipeMedia).values(rows)
            )

    # ----------------------------
    # Activity Log
    # ----------------------------
    session.add(
        Activity(
            user_id=user.id,
            verb="recipe.edit",
            subject_table="recipes",
            subject_id=recipe.id,
            payload=None,
        )
    )

    await session.commit()

    return {"ok": True, "recipe_id": recipe.id}
