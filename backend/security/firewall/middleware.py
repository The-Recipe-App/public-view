# security/firewall/middleware.py

import asyncio
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from cerberus.core.engine import cerberus
from cerberus.core.types import ThreatEvent, ThreatKey
from cerberus.core.enums import Decision
from cerberus.core.telemetry import now_us

from security.config import FirewallConfig
from security.firewall.utils.utils import get_client_ip
from security.firewall.rate_limit import hit_rate_limit
from security.firewall.blacklist import is_blocked, promote_permanent_block
from security.firewall.strike_engine import escalate_if_needed
from security.firewall.exceptions import FirewallExceptions

from security.policies.cache import resolve_policy_cached
from security.policies.definitions import POLICIES

from utilities.common.common_utility import debug_print


class FirewallMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_us = now_us()

        path = request.url.path
        method = request.method

        # 1. Exemptions
        if FirewallExceptions.is_exempt(path, method):
            debug_print(f"EXEMPT {method} {path}", color="cyan", tag="FIREWALL")
            return await call_next(request)

        # 2. Resolve policy
        policy = resolve_policy_cached(path)
        policy_def = POLICIES[policy]
        debug_print(f"{method} {path} -> policy={policy}", color="cyan", tag="FIREWALL")

        # 3. Identify client
        ip = get_client_ip(request)

        # 4. Fingerprint
        fingerprint = None
        if policy_def.fingerprint_required:
            fingerprint = request.headers.get(FirewallConfig.FINGERPRINT_HEADER)

        # ───────── CERBERUS PRE ─────────
        ip_key = hash(ip)
        fp_key = hash(fingerprint) if fingerprint else 0
        user_id = 0

        event = ThreatEvent(
            ts_us=start_us,
            ip=ip_key,
            path_hash=hash(path),
            method=hash(method),
            status=0,
            latency_us=0,
            fingerprint=fp_key,
            user_id=user_id,
        )

        key = ThreatKey(ip=ip_key, fingerprint=fp_key, user_id=user_id)

        cerberus.observe(event)
        decision = cerberus.decide(key)

        # 5. Hard DB blocks
        blocked, reason = await is_blocked(ip=ip, fingerprint=fingerprint)
        if blocked:
            debug_print(f"BLOCKED {ip} reason={reason}", color="red", tag="FIREWALL")
            return JSONResponse(
                {"error": "Access blocked", "reason": reason},
                status_code=403,
            )

        # 6. Rate limit key
        if policy_def.escalation_scope == "ROUTE":
            rate_key = f"{policy}:ROUTE:{path}:{ip}"
        elif policy_def.escalation_scope == "IP_FINGERPRINT":
            rate_key = f"{policy}:IP_FP:{ip}:{fingerprint or 'no-fp'}"
        else:
            rate_key = f"{policy}:IP:{ip}"

        # 7. Rate limiting
        allowed = await hit_rate_limit(
            key=rate_key,
            limit=policy_def.requests,
            window=policy_def.window.total_seconds(),
        )

        if not allowed:
            debug_print(f"RATE LIMIT HIT {rate_key}", color="yellow", tag="FIREWALL")

            promoted, escalation_msg = await escalate_if_needed(
                ip=ip,
                policy_name=policy.value,
                scope=policy_def.escalation_scope,
                window=policy_def.window.total_seconds(),
                threshold=policy_def.escalate_after,
                path=path,
                fingerprint=fingerprint,
                promote_to_permanent=policy_def.global_block,
            )

            if promoted and policy_def.global_block:
                return JSONResponse(
                    {"error": "Permanently blocked", "reason": escalation_msg},
                    status_code=403,
                )

            return JSONResponse(
                {
                    "error": "Too many requests",
                    "message": "You are temporarily blocked. Continued abuse will escalate.",
                },
                status_code=429,
            )

        # ───────── CERBERUS ENFORCEMENT ─────────
        if decision == Decision.KILL:
            debug_print(f"KILL {ip}", color="red", tag="CERBERUS")
            await promote_permanent_block(ip, fingerprint, reason="Cerberus autonomous termination")
            return JSONResponse(
                {"error": "Access permanently blocked by adaptive security"},
                status_code=403,
            )

        if decision == Decision.THROTTLE:
            debug_print(f"THROTTLE {ip}", color="yellow", tag="CERBERUS")
            await asyncio.sleep(0.25)

        if decision == Decision.CHALLENGE:
            debug_print(f"CHALLENGE {ip}", color="magenta", tag="CERBERUS")
            return JSONResponse(
                {"error": "Additional verification required"},
                status_code=401,
            )

        # 8. Forward request
        response = await call_next(request)

        # ───────── CERBERUS POST ─────────
        event.status = response.status_code
        event.latency_us = now_us() - start_us
        cerberus.observe(event)

        return response
