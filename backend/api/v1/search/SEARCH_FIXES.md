# Search audit & fixes — automated pass

Repository scanned under: `/mnt/data/for_search_unzipped`

## What I did
1. Unzipped the repository and scanned all 194 files.
2. Located search components under `api/v1/search` including:
   - `search.py` (FastAPI router)
   - `services/search_service.py` (search logic)
   - `services/embed.py` (embeddings via sentence-transformers)
   - `backfill.py` (reindex endpoint)
3. Ran static checks (Python syntax compile) — no syntax errors detected in Python files.
4. Created SQL migration and a fallback Python hybrid search module to ensure search works
   even if pgvector / Postgres vector indexes are not present.
5. Saved this report and the files:
   - `migrations/001_search_setup.sql`
   - `api/v1/search/services/patches/fallback_hybrid_search.py`

## Findings (high level)
- The project uses `sentence-transformers` for embeddings (local model `all-MiniLM-L6-v2`).
  Ensure `sentence-transformers` and its dependencies are installed.
- The search service references `pgvector` and Postgres `tsvector`/FTS (see `search_service.py` and `search.py`).
  The database needs the `vector` extension (pgvector) and the `tsvector` column/index for proper hybrid search.
- No Python syntax errors were found, but runtime issues could still exist if dependencies or DB extensions are missing.
- There is a reindex endpoint (`POST /api/v1/search/reindex`) — good. Running it will backfill embeddings but requires the sentence-transformers model to be available.

## Recommended next steps (apply in this order)
1. Add/ensure Python dependencies in requirements.txt / pyproject.toml:
   - sentence-transformers
   - numpy
   - cachetools
   - sqlalchemy (if not present)
   - asyncpg (if using async Postgres)
   - psycopg[binary] or similar
2. Run the SQL migration at `migrations/001_search_setup.sql` on the production DB (or staging first).
3. If pgvector is not available or you can't add the extension, use the fallback hybrid search implementation:
   - Copy `api/v1/search/services/patches/fallback_hybrid_search.py` to `api/v1/search/services/fallback_hybrid_search.py`
   - Integrate into `search_service.hybrid_search()` such that if vector index not available, it calls `hybrid_search_fallback` with a candidate SQL that performs `to_tsquery()` keyword filtering.
4. Run the reindex endpoint to populate embeddings:
   `POST /api/v1/search/reindex` (ensure the app can access the model and DB)
5. Monitor performance; for large datasets prefer using FAISS, Milvus, or a dedicated vector DB.

## Files I added
- `migrations/001_search_setup.sql`
- `api/v1/search/services/patches/fallback_hybrid_search.py`