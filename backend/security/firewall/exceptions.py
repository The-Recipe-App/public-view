class FirewallExceptions:
    EXCLUDED_METHODS = {"OPTIONS"}

    EXCLUDED_PATHS = {
        "/",
        "/status",
        "/auth/login",
        "/auth/register",
    }

    EXCLUDED_PREFIXES = (
        "/docs",
        "/redoc",
        "/openapi",
        "/static",
    )

    @classmethod
    def is_exempt(cls, path: str, method: str) -> bool:
        if method in cls.EXCLUDED_METHODS:
            return True
        if path in cls.EXCLUDED_PATHS:
            return True
        return any(path.startswith(p) for p in cls.EXCLUDED_PREFIXES)
