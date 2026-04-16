# api/v1/recipes/report.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database.main.core.session import get_async_session
from database.main.core.models import (
    User,
    Recipe,
    RecipeReport,
    Activity,
)

from api.v1.auth.utils.dependencies import get_current_user
from pydantic import BaseModel, Field

router = APIRouter()


class ReportRecipeReq(BaseModel):
    reason: str = Field(..., min_length=3)
    details: str | None = None


@router.post("/{recipe_id}/report", status_code=201)
async def report_recipe(
    recipe_id: int,
    payload: ReportRecipeReq,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    recipe = await session.get(Recipe, recipe_id)

    if not recipe or recipe.is_deleted:
        raise HTTPException(status_code=404, detail="Recipe not found")

    # ✅ Prevent duplicate reports
    existing = await session.scalar(
        RecipeReport.__table__.select().where(
            RecipeReport.recipe_id == recipe.id,
            RecipeReport.reporter_id == user.id,
        )
    )

    if existing:
        raise HTTPException(status_code=400, detail="Already reported")

    # ✅ Store report in moderation table
    report = RecipeReport(
        recipe_id=recipe.id,
        reporter_id=user.id,
        reason=payload.reason,
        details=payload.details,
    )
    session.add(report)

    # ✅ Log Activity
    session.add(
        Activity(
            user_id=user.id,
            verb="recipe.report",
            subject_table="recipes",
            subject_id=recipe.id,
            payload={
                "reason": payload.reason,
                "details": payload.details,
            },
        )
    )

    await session.commit()

    return {"ok": True, "reported": True}
