from __future__ import annotations
import time
import threading
from typing import Optional, List
from .types import ThreatEvent
from utilities.common.common_utility import debug_print


def now_us() -> int:
    return int(time.perf_counter_ns() // 1000)


class TelemetryRing:
    __slots__ = ("_size", "_mask", "_buffer", "_write", "_read")

    def __init__(self, size: int = 1 << 20):
        if size & (size - 1) != 0:
            raise ValueError("Ring size must be power of two")

        self._size = size
        self._mask = size - 1
        self._buffer: List[Optional[ThreatEvent]] = [None] * size
        self._write = 0
        self._read = 0

    # HOT PATH (O(1), no locks)
    def push(self, event: ThreatEvent) -> None:
        idx = self._write & self._mask
        self._buffer[idx] = event
        self._write += 1
        debug_print(
            f"Telemetry received ip={event.ip} path={event.path_hash}",
            tag="TELEMETRY",
            color="cyan",
        )

    # BRAIN PATH (batch)
    def pop_batch(self, max_items: int = 4096) -> List[ThreatEvent]:
        out: List[ThreatEvent] = []

        w = self._write
        r = self._read
        available = w - r

        if available <= 0:
            return out

        n = min(available, max_items)

        for _ in range(n):
            idx = r & self._mask
            ev = self._buffer[idx]
            if ev is not None:
                out.append(ev)
            self._buffer[idx] = None
            r += 1

        self._read = r
        if out:
            debug_print(
                f"Processing batch size={len(out)}",
                tag="TELEMETRY",
                color="blue",
            )

        return out


class TelemetryConsumer(threading.Thread):
    def __init__(self, ring: TelemetryRing, handler, poll_ms: int = 5):
        super().__init__(daemon=True)
        self.ring = ring
        self.handler = handler
        self.poll = poll_ms / 1000
        self._run = True

    def run(self):
        while self._run:
            batch = self.ring.pop_batch()
            if batch:
                self.handler(batch)
            else:
                time.sleep(self.poll)

    def stop(self):
        self._run = False
