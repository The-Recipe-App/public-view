# security/db/init_db.py
from database.security.core.models import Base
from database.security.core.session import engine
from security.firewall.utils.utils import preload_blacklist_cache
from utilities.common.common_utility import debug_print

async def bootstrap_security_db():
    debug_print("Initializing Security Database...", color="cyan")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    debug_print("Security Database initialized.", color="cyan")
    await preload_blacklist_cache()

    await engine.dispose()

