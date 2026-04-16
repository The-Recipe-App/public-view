from __future__ import annotations
from utilities.common.common_utility import debug_print


class RiskAccumulator:
    __slots__ = ("score", "momentum", "decay")

    def __init__(self, decay: float = 0.98):
        self.score = 0.0
        self.momentum = 0.0
        self.decay = decay

    def update(self, anomaly: float) -> float:
        """
        anomaly: positive-only deviation (0 = normal, >0 = abnormal)
        """

        # Momentum = how fast threat is accelerating
        self.momentum = 0.9 * self.momentum + 0.1 * anomaly

        # Risk integrates anomaly + momentum, but decays naturally
        self.score = self.score * self.decay + anomaly + self.momentum

        if self.score < 0:
            self.score = 0.0

        debug_print(
            f"Risk score={self.score:.2f} momentum={self.momentum:.2f}",
            tag="RISK",
            color="yellow",
        )

        return self.score
