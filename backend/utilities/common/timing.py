# utilities/common/timing.py
import time
import logging
log = logging.getLogger("timing")

class Timer:
    def __init__(self, label: str = "Timer"):
        self.label = label
        self.start = time.perf_counter()
    def step(self, msg: str):
        now = time.perf_counter()
        log.info("%s: %s -> %.3fms", self.label, msg, (now - self.start) * 1000)
        self.start = now
    def finish(self, msg: str):
        now = time.perf_counter()
        log.info("%s: %s -> %.3fms (total)", self.label, msg, (now - self.start) * 1000)
