# database/main/core/bootstrap_utils.py
from sqlalchemy import inspect
from sqlalchemy.engine import Connection

def remove_existing_indexes_from_metadata_sync(conn: Connection, metadata):
    """
    Remove Index objects from metadata.tables[*].indexes when the index already exists in the DB.
    This prevents SQLAlchemy from issuing CREATE INDEX for indexes already present.
    """
    inspector = inspect(conn)
    for table in metadata.sorted_tables:
        try:
            db_indexes = {idx["name"] for idx in inspector.get_indexes(table.name)}
        except Exception:
            # table might not exist yet - that's fine
            db_indexes = set()

        for idx in list(table.indexes):
            if idx.name is None:
                continue
            if idx.name in db_indexes:
                # remove this Index object so create_all() won't try to recreate it
                table.indexes.discard(idx)
