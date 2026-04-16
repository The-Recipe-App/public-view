from functools import lru_cache
from security.policies.resolver import resolve_domain_from_path
from security.policies.domains import DOMAIN_POLICY_MAP
from security.policies.enums import RateLimitPolicy

@lru_cache(maxsize=1024)
def resolve_policy_cached(path: str) -> RateLimitPolicy:
    domain = resolve_domain_from_path(path)
    return DOMAIN_POLICY_MAP.get(domain, RateLimitPolicy.PUBLIC)
    