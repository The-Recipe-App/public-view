from dataclasses import dataclass
from datetime import timedelta
from security.policies.enums import RateLimitPolicy

@dataclass(frozen=True)
class PolicyDefinition:
    requests: int
    window: timedelta

    escalate_after: int
    escalation_scope: str

    fingerprint_required: bool
    global_block: bool

POLICIES = {
    RateLimitPolicy.PUBLIC: PolicyDefinition(
        requests=120,
        window=timedelta(minutes=1),
        escalate_after=10,
        escalation_scope="ROUTE",
        fingerprint_required=False,
        global_block=False,
    ),
    RateLimitPolicy.AUTH: PolicyDefinition(
        requests=30,
        window=timedelta(minutes=1),
        escalate_after=5,
        escalation_scope="IP",
        fingerprint_required=False,
        global_block=True,
    ),
    RateLimitPolicy.REGISTRATION: PolicyDefinition(
        requests=5,
        window=timedelta(minutes=30),
        escalate_after=10,
        escalation_scope="IP_FINGERPRINT",
        fingerprint_required=True,
        global_block=True,
    ),
    RateLimitPolicy.OTP: PolicyDefinition(
        requests=5,
        window=timedelta(minutes=10),
        escalate_after=2,
        escalation_scope="IP_FINGERPRINT",
        fingerprint_required=True,
        global_block=False,
    ),
    RateLimitPolicy.USER: PolicyDefinition(
        requests=120,
        window=timedelta(minutes=1),
        escalate_after=10,
        escalation_scope="ROUTE",
        fingerprint_required=False,
        global_block=False,
    ),
    RateLimitPolicy.ADMIN: PolicyDefinition(
        requests=20,
        window=timedelta(minutes=1),
        escalate_after=3,
        escalation_scope="IP",
        fingerprint_required=True,
        global_block=True,
    ),
    RateLimitPolicy.INTERNAL: PolicyDefinition(
        requests=1000,
        window=timedelta(minutes=1),
        escalate_after=0,
        escalation_scope="IP_FINGERPRINT",
        fingerprint_required=False,
        global_block=False,
    )
}