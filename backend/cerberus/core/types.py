from __future__ import annotations
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class ThreatKey:
    ip: int
    fingerprint: int
    user_id: int


@dataclass(slots=True)
class ThreatEvent:
    ts_us: int
    ip: int
    path_hash: int
    method: int
    status: int
    latency_us: int
    fingerprint: int
    user_id: int
