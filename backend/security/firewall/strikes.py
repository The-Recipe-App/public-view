# security/firewall/strikes.py
import time
from collections import defaultdict
from typing import Dict, Tuple

# key -> {count, first_seen}
_strikes: Dict[str, Dict[str, float]] = defaultdict(lambda: {
    "count": 0,
    "first_seen": time.time(),
})

def register_strike(
    identity_key: str,
    window: float,
    threshold: int,
) -> bool:
    """
    Register a strike for an identity and check if escalation threshold is reached.

    Args:
        identity_key: Unique key based on escalation scope
                        (e.g. "IP:1.2.3.4", "IP_FP:1.2.3.4:abcd1234", "ROUTE:/auth/login:1.2.3.4")
        window: Rolling strike window in seconds (policy-driven)
        threshold: Escalation threshold (policy-driven)

    Returns:
        True  -> Escalation threshold reached (promote to next level)
        False -> Still below threshold
    """
    now = time.time()
    record = _strikes[identity_key]

    # Reset window if expired
    if now - record["first_seen"] > window:
        record["count"] = 0
        record["first_seen"] = now

    record["count"] += 1

    if record["count"] >= threshold:
        # Clear record after promotion
        _strikes.pop(identity_key, None)
        return True

    return False
