"""
Standalone backfill script — generate embeddings for all existing recipes.

Usage:
    python scripts/backfill_embeddings.py

Run this ONCE after the migration, then embeddings are kept up to date
automatically via embed_and_save() in your create/update recipe endpoints.

Env vars required (same as your FastAPI app):
    DATABASE_URL=postgresql+asyncpg://user:pass@host/dbname
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

# Allow running from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from api.v1.search.services.embed import build_recipe_text, embed_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

DATABASE_URL = os.environ["DATABASE_URL"]   # fail fast if not set


async def backfill() -> None:
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Fetch all recipes missing embeddings
        result = await session.execute(
            text("""
                SELECT id, title, description, ingredients_text, cuisine
                FROM recipes
                WHERE embedding IS NULL
                ORDER BY id
            """)
        )
        rows = result.mappings().all()
        total = len(rows)

        if total == 0:
            logger.info("All recipes already have embeddings. Nothing to do.")
            return

        logger.info(f"Backfilling embeddings for {total} recipes...")

        success = 0
        failed = 0

        for i, row in enumerate(rows, start=1):
            recipe_id = row["id"]
            try:
                recipe_text = build_recipe_text(
                    title=row["title"],
                    description=row.get("description"),
                    ingredients_text=row.get("ingredients_text"),
                    cuisine=row.get("cuisine"),
                )
                vector = embed_text(recipe_text)

                await session.execute(
                    text("UPDATE recipes SET embedding = :vec WHERE id = :id"),
                    {"vec": str(vector), "id": recipe_id},
                )

                success += 1

                if i % 10 == 0 or i == total:
                    await session.commit()
                    logger.info(f"  Progress: {i}/{total} ({success} ok, {failed} failed)")

            except Exception as exc:
                failed += 1
                logger.error(f"  Failed recipe {recipe_id}: {exc}")
                await session.rollback()

        # Final commit for any remainder
        await session.commit()

    await engine.dispose()

    logger.info("=" * 50)
    logger.info(f"Backfill complete: {success} succeeded, {failed} failed.")


if __name__ == "__main__":
    asyncio.run(backfill())