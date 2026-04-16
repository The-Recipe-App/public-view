from enum import IntEnum, auto


class ThreatState(IntEnum):
    NORMAL = 0
    WATCH = 1
    CHALLENGE = 2
    RESTRICT = 3
    TERMINATE = 4


class Decision(IntEnum):
    ALLOW = 0
    CHALLENGE = 1
    THROTTLE = 2
    BLOCK = 3
    KILL = 4
