from __future__ import annotations
import math
from utilities.common.common_utility import debug_print


class AdaptiveBaseline:
    __slots__ = ("mean", "var", "alpha")

    def __init__(self, alpha: float = 0.05):
        self.mean = 0.0
        self.var = 1.0
        self.alpha = alpha

    def update(self, x: float) -> float:
        # EWMA update
        delta = x - self.mean
        self.mean += self.alpha * delta
        self.var = (1 - self.alpha) * (self.var + self.alpha * delta * delta)

        # Return z-score (anomaly strength)
        std = math.sqrt(self.var) if self.var > 1e-6 else 1.0
        debug_print(
            f"Baseline mean={self.mean:.3f} var={self.var:.3f} z={delta/std:.3f}",
            tag="BASELINE",
            color="green",
        )

        return delta / std
