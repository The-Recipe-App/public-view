from enum import Enum

class  RateLimitPolicy(str, Enum):
    PUBLIC = "PUBLIC"
    AUTH = "AUTH"
    REGISTRATION = "REGISTRATION"
    OTP = "OTP"
    USER = "USER"
    ADMIN = "ADMIN"
    INTERNAL = "INTERNAL"