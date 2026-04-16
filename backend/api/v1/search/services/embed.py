"""
Embedding service for Forkit semantic search.

Uses all-MiniLM-L6-v2 (~80MB) — fast, accurate, 384-dim output.
Model is loaded once at startup and reused across all requests.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import TYPE_CHECKING

from sentence_transformers import SentenceTransformer

from fastapi import Request

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)

@lru_cache(maxsize=1)
def get_model(app):
    return app.state.embedding_model


def embed_text(text: str, request: Request | None = None, app=None) -> list[float]:
    resolved_app = app if app is not None else request.app
    model = get_model(app=resolved_app)
    vector: np.ndarray = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


def build_recipe_text(
    title: str,
    body: str | None = None,
    ingredient_names: list[str] | None = None,
) -> str:
    parts = [title, title]  # repeat title for weight
    if body:
        parts.append(body)
    if ingredient_names:
        parts.append(" ".join(ingredient_names))
    return ". ".join(filter(None, parts))