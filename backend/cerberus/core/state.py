from __future__ import annotations
from .enums import ThreatState
from utilities.common.common_utility import debug_print


class StateMachine:
    __slots__ = ("state",)

    def __init__(self):
        self.state = ThreatState.NORMAL

    def transition(self, risk: float) -> ThreatState:
        if risk > 32:
            self.state = ThreatState.TERMINATE
        elif risk > 27:
            self.state = ThreatState.RESTRICT
        elif risk > 15:
            self.state = ThreatState.CHALLENGE
        elif risk > 8:
            self.state = ThreatState.WATCH
        else:
            # graceful recovery
            if self.state != ThreatState.NORMAL:
                self.state = ThreatState(self.state - 1)

        debug_print(
            f"State transitioned to {self.state.name} (risk={risk:.2f})",
            tag="STATE",
            color="magenta",
        )

        return self.state
