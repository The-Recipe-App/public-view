"""
api/v1/search/search.py
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database.main.core.session import get_async_session
from api.v1.search.services.search_service import hybrid_search, invalidate_cache, embed_and_save
from utilities.common.common_utility import debug_print

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/search", tags=["search"])


# ── Response schema ───────────────────────────────────────────────────────────

class RecipeSearchResult(BaseModel):
    id: int
    title: str
    body: str | None
    cuisine: str | None
    difficulty: str | None
    prep_time_mins: int | None
    cook_time_mins: int | None
    likes_count: int
    views_count: int
    score: int          # recipe vote score
    search_score: float # semantic relevance

    class Config:
        from_attributes = True


class SearchResponse(BaseModel):
    query: str
    total: int
    results: list[RecipeSearchResult]


async def require_model_ready(request: Request):
    if not request.app.state.model_ready.is_set():
        raise HTTPException(
            status_code=503,
            detail="Search is temporarily unavailable. Model is still loading.",
        )

# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1, max_length=200),
    cuisine: str | None = Query(None, description="Filter by cuisine"),
    limit: int = Query(default=20, ge=1, le=50),
    db: AsyncSession = Depends(get_async_session),
    request: Request = None,
    _: None = Depends(require_model_ready),
) -> SearchResponse:
    if not q.strip():
        raise HTTPException(status_code=422, detail="Query cannot be empty.")

    results = await hybrid_search(query=q, db=db, limit=limit, cuisine=cuisine, request=request)
    return SearchResponse(
        query=q,
        total=len(results),
        results=[RecipeSearchResult(**r) for r in results],
    )

async def _reindex(app) -> int:
    from database.main.core.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("""
                SELECT id, title, body, cuisine
                FROM recipes
                WHERE embedding IS NULL
                ORDER BY id
            """)
        )
        rows = result.mappings().all()

        if not rows:
            debug_print("All recipes already have embeddings.", color="green", tag="INFO")
            return 0

        processed = 0
        for row in rows:
            try:
                await embed_and_save(
                    recipe_id=row["id"],
                    title=row["title"],
                    body=row.get("body"),
                    cuisine=row.get("cuisine"),
                    db=db,
                    app=app,
                )
                processed += 1
            except Exception as exc:
                debug_print(f"Failed to embed recipe {row['id']}: {exc}", color="red", tag="ERROR")

        await db.commit()

        invalidate_cache()
        debug_print(f"Reindex complete. Processed {processed} recipes.", color="green", tag="INFO")
        return processed

@router.post("/reindex", status_code=202)
async def reindex(
    _: None = Depends(require_model_ready),
) -> dict:
    processed = await _reindex()
    return {"message": "Reindex complete.", "processed": processed}