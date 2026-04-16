# database/core/init_db.py

from database.main.core.session import engine
from database.main.core.base import Base
from database.main.core.models import *  # ensure models are imported
from database.main.core.bootstrap.utils import remove_existing_indexes_from_metadata_sync
from utilities.common.common_utility import debug_print

async def bootstrap_main_db():
    async with engine.begin() as conn:
        # remove index objects that already exist in the DB
        await conn.run_sync(lambda sync_conn: remove_existing_indexes_from_metadata_sync(sync_conn, Base.metadata))
        # now safe to create tables + any remaining indexes
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(bind=sync_conn))
        debug_print("All database tables created.", color="green")
