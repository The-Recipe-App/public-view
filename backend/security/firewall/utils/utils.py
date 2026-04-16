from database.security.core.session import security_session_ctx
from database.security.core.models import SecurityBlock
from sqlalchemy import select
from fastapi import Request
from security.firewall.utils.cache import cache_block
from utilities.common.common_utility import debug_print


async def preload_blacklist_cache():
    debug_print("Preloading active security blocks into cache...", color="cyan", tag="FIREWALL")

    async with security_session_ctx() as session:
        result = await session.execute(
            select(SecurityBlock).where(SecurityBlock.is_active.is_(True))
        )
        for block in result.scalars():
            await cache_block(block)

    debug_print("Preloading complete.", color="cyan", tag="FIREWALL")


def get_client_ip(request: Request) -> str:
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host or "unknown"
