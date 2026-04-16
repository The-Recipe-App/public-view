from datetime import datetime

from database.security.core.session import security_session_ctx
from database.security.core.models import SecurityBlock
from security.firewall.utils.cache import is_cached_blocked, cache_block

from utilities.helpers.task_manager.manager import task_manager, TaskType
from utilities.common.common_utility import debug_print


async def is_blocked(ip: str, fingerprint: str | None = None):
    return await is_cached_blocked(ip, fingerprint)


async def _persist_block(block: SecurityBlock):
    debug_print("Adding entry to DB...", color="cyan", tag="FIREWALL")

    async with security_session_ctx() as session:
        session.add(block)
        await session.commit()

    debug_print("Added entry to DB.", color="cyan", tag="FIREWALL")


async def add_block(
    ip: str,
    policy_name: str,
    scope: str,
    reason: str,
    fingerprint_hash: str | None = None,
    route: str | None = None,
    is_permanent: bool = False,
    expires_at: datetime | None = None,
):
    block = SecurityBlock(
        ip_address=ip,
        fingerprint_hash=fingerprint_hash,
        route=route,
        policy_name=policy_name,
        scope=scope,
        is_permanent=is_permanent,
        is_active=True,
        reason=reason,
        expires_at=expires_at,
    )

    # 1. Instant in-memory protection (no DB wait)
    await cache_block(block)

    # 2. Background persistence (does not block request)
    await task_manager.add_task(
        _persist_block,
        args=(block,),
        run_once_and_forget=True,
        task_type=TaskType.ASYNC,
    )


async def promote_permanent_block(
    ip: str,
    fingerprint: str | None = None,
    reason: str = "Cerberus autonomous termination",
):
    debug_print(
        f"CERBERUS PERMA-BAN ip={ip} fp={fingerprint}",
        color="red",
        tag="CERBERUS",
    )

    await add_block(
        ip=ip,
        policy_name="CERBERUS",
        scope="IP_FINGERPRINT" if fingerprint else "IP",
        reason=reason,
        fingerprint_hash=fingerprint,
        is_permanent=True,
        expires_at=None,
    )
