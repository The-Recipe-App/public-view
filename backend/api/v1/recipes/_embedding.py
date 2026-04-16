# api/v1/recipes/_embedding.py

import asyncio
from fastapi import Request
from database.main.core.session import AsyncSessionLocal
from api.v1.search.services.search_service import embed_and_save
from utilities.common.common_utility import debug_print
from utilities.helpers.task_manager.manager import task_manager

async def _schedule_embedding(
    *,
    request: Request,
    recipe_id: int,
    title: str,
    body: str | None,
    ingredient_names: list[str] | None,
) -> None:
    """
    Fire-and-forget: schedule embedding after the response is sent.
    Opens its own session so the caller's session can close cleanly.
    embed_text() is synchronous/CPU-bound so embed_and_save runs it
    via run_in_executor internally — doesn't block the event loop.
    """
    await task_manager.add_task(
        func=_embed_task,
        recipe_id=recipe_id,
        title=title,
        body=body,
        ingredient_names=ingredient_names,
        request=request,
        run_once_and_forget=True,
        name="embedding",
    )


async def _embed_task(
    *,
    recipe_id: int,
    title: str,
    body: str | None,
    ingredient_names: list[str] | None,
    request: Request,
) -> None:
    try:
        async with AsyncSessionLocal() as session:
            await embed_and_save(
                recipe_id=recipe_id,
                title=title,
                body=body,
                ingredient_names=ingredient_names,
                db=session,
                request=request,  # ← add this back
            )
    except Exception as e:
        debug_print(f"[embedding] Failed for recipe {recipe_id}: {e}", tag="ERROR", color="red")