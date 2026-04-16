from datetime import datetime, timezone
from cachetools import TTLCache
import asyncio
from utilities.common.common_utility import debug_print

# Max 50k entries, auto-expire after 24h
BLOCK_CACHE = TTLCache(maxsize=50_000, ttl=24 * 3600)
CACHE_LOCK = asyncio.Lock()


def _now():
    return datetime.now(timezone.utc)


def make_key(ip: str, fingerprint: str | None):
    return (ip, fingerprint or "*")


async def cache_block(block):
    async with CACHE_LOCK:
        BLOCK_CACHE[make_key(block.ip_address, block.fingerprint_hash)] = {
            "reason": block.reason,
            "is_permanent": block.is_permanent,
            "expires_at": block.expires_at,
        }
        debug_print(f"Added {block.ip_address} to cache.", color="cyan", tag="FIREWALL")


async def is_cached_blocked(ip: str, fingerprint: str | None):
    async with CACHE_LOCK:
        # Check exact (IP+fingerprint)
        key = make_key(ip, fingerprint)
        entry = BLOCK_CACHE.get(key)

        # Check global IP block
        if not entry:
            key = make_key(ip, None)
            entry = BLOCK_CACHE.get(key)

        if not entry:
            return False, None

        if entry["is_permanent"]:
            return True, entry["reason"]

        if entry["expires_at"] and entry["expires_at"] > _now():
            return True, entry["reason"]

        # Expired → remove
        BLOCK_CACHE.pop(key, None)
        return False, None
