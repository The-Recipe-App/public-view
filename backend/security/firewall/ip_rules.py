from sqlalchemy import select
from database.security.core.session import security_session_ctx
from database.security.core.models import PermanentBlacklist

async def is_permanently_blocked(ip: str) -> bool:
    async with security_session_ctx() as session:
        res = await session.execute(
            select(PermanentBlacklist).where(PermanentBlacklist.ip_address == ip)
        )
        return res.scalar_one_or_none() is not None
