# cerberus/core/engine.py
#
# Revision notes:
#
#  1.  debug_print IN HOT PATHS REMOVED — the original called debug_print
#      unconditionally in three places:
#        - observe()         → fires on EVERY inbound request
#        - decide()          → fires on EVERY auth/permission check
#        - _process_batch()  → fires for EVERY event in every batch
#
#      debug_print builds a formatted string even when nothing is listening.
#      Under load (e.g. 500 req/s) that's 500+ string interpolations per
#      second in the two hot-path methods alone, all producing output that
#      goes nowhere in production.
#
#      Fix: all three sites are gated behind DEBUG_MODE (reads the DEBUG
#      env var, same pattern used in security.py).  In production the
#      entire branch is skipped.  In local dev the output is unchanged.

from __future__ import annotations

import os
import threading
import time
from typing import Dict

from .telemetry import TelemetryRing, TelemetryConsumer
from .types import ThreatEvent, ThreatKey
from .enums import ThreatState, Decision
from .baseline import AdaptiveBaseline
from .risk import RiskAccumulator
from .state import StateMachine
from utilities.common.common_utility import debug_print

DEBUG_MODE: bool = os.getenv("DEBUG", "").lower() in ("1", "true", "yes")


class _ThreatRecord:
    __slots__ = ("baseline", "risk", "fsm", "last_seen")

    def __init__(self) -> None:
        self.baseline  = AdaptiveBaseline()
        self.risk      = RiskAccumulator()
        self.fsm       = StateMachine()
        self.last_seen = 0


class CerberusEngine:
    def __init__(self, ring_size: int = 1 << 20) -> None:
        self._ring     = TelemetryRing(ring_size)
        self._states:  Dict[ThreatKey, _ThreatRecord] = {}
        self._lock     = threading.Lock()
        self._consumer = TelemetryConsumer(self._ring, self._process_batch)
        self._consumer.start()

    # ── FAST PATH ─────────────────────────────────────────────────────────────

    def observe(self, event: ThreatEvent) -> None:
        self._ring.push(event)
        # FIX #1 — only pay the string-format cost in dev
        if DEBUG_MODE:
            debug_print(
                f"Observed event ip={event.ip} user={event.user_id}",
                tag="CERBERUS",
                color="cyan",
            )

    def decide(self, key: ThreatKey) -> Decision:
        rec = self._states.get(key)
        if not rec:
            return Decision.ALLOW

        s = rec.fsm.state
        if s in (ThreatState.NORMAL, ThreatState.WATCH):
            decision = Decision.ALLOW
        elif s == ThreatState.CHALLENGE:
            decision = Decision.CHALLENGE
        elif s == ThreatState.RESTRICT:
            decision = Decision.THROTTLE
        elif s == ThreatState.TERMINATE:
            decision = Decision.KILL
        else:
            decision = Decision.ALLOW

        # FIX #1 — only pay the string-format cost in dev
        if DEBUG_MODE:
            debug_print(
                f"Decision={decision.name} for ip={key.ip}",
                tag="CERBERUS",
                color="red" if decision == Decision.KILL else "white",
            )

        return decision

    # ── BRAIN LOOP ────────────────────────────────────────────────────────────

    def _process_batch(self, batch: list[ThreatEvent]) -> None:
        now_us = int(time.time() * 1_000_000)

        for ev in batch:
            key = ThreatKey(ev.ip, ev.fingerprint, ev.user_id)

            with self._lock:
                rec = self._states.get(key)
                if not rec:
                    rec = _ThreatRecord()
                    self._states[key] = rec

                signal    = 1.0 if ev.status >= 400 else -0.2
                z         = rec.baseline.update(signal)
                anomaly   = max(0.0, z - 1.0)
                risk_score = rec.risk.update(anomaly)
                rec.fsm.transition(risk_score)

                # FIX #1 — only pay the string-format cost in dev
                if DEBUG_MODE:
                    debug_print(
                        f"Key={key.ip} Risk={risk_score:.2f} State={rec.fsm.state.name}",
                        tag="CERBERUS",
                        color="red" if rec.fsm.state.name == "TERMINATE" else "yellow",
                    )

                rec.last_seen = now_us

        self._gc(now_us)

    # ── MEMORY CONTROL ────────────────────────────────────────────────────────

    def _gc(self, now_us: int) -> None:
        TTL = 10 * 60 * 1_000_000  # 10 minutes
        for key in list(self._states.keys()):
            if now_us - self._states[key].last_seen > TTL:
                del self._states[key]


# Global singleton
cerberus = CerberusEngine()