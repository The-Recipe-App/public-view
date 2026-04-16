# api/v1/recipes/admin.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from database.main.core.session import get_async_session
from database.main.core.models import User, Recipe, Vote, RecipeView, Share, Bookmark, Activity
from api.v1.auth.utils.dependencies import get_current_user

router = APIRouter()

@router.post("/{recipe_id}/lock")
async def lock_recipe(recipe_id: int, should_lock: bool = Query(True), user: User = Depends(get_current_user), session: AsyncSession = Depends(get_async_session)):
    if not user.can_moderate():
        raise HTTPException(status_code=403, detail="Not authorized")
    recipe = await session.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    recipe.is_locked = bool(should_lock)
    session.add(Activity(user_id=user.id, verb="recipe.lock" if should_lock else "recipe.unlock", subject_table="recipes", subject_id=recipe_id, payload=None))
    await session.commit()
    return {"ok": True, "locked": recipe.is_locked}

@router.post("/admin/{recipe_id}/recompute_counters")
async def recompute_counters(recipe_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_async_session)):
    if not user.can_moderate():
        raise HTTPException(status_code=403, detail="Not authorized")
    likes = await session.scalar(select(func.count()).select_from(Vote).where(Vote.target_type == 0, Vote.target_id == recipe_id, Vote.value == 1))
    views = await session.scalar(select(func.count()).select_from(RecipeView).where(RecipeView.recipe_id == recipe_id))
    shares = await session.scalar(select(func.count()).select_from(Share).where(Share.recipe_id == recipe_id))
    bookmarks = await session.scalar(select(func.count()).select_from(Bookmark).where(Bookmark.recipe_id == recipe_id))
    recipe = await session.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    recipe.likes_count = likes or 0
    recipe.views_count = views or 0
    recipe.shares_count = shares or 0
    recipe.bookmarks_count = bookmarks or 0
    session.add(recipe)
    await session.commit()
    return {"ok": True, "likes": recipe.likes_count, "views": recipe.views_count}
