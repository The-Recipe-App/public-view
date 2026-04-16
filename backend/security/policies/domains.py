from security.policies.enums import RateLimitPolicy

DOMAIN_POLICY_MAP = {
    "health": RateLimitPolicy.INTERNAL,

    "auth": RateLimitPolicy.AUTH,
    "auth.register": RateLimitPolicy.REGISTRATION,
    "auth.otp": RateLimitPolicy.OTP,

    "users": RateLimitPolicy.USER,
    "admin": RateLimitPolicy.ADMIN,

    "public": RateLimitPolicy.PUBLIC,
}