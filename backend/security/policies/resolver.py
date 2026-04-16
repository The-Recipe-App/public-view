def resolve_domain_from_path(path: str) -> str:
    path = path.lower()

    if "/health" in path:
        return "health"
    
    if "/auth" in path:
        if "register" in path:
            return "auth.register"
        if "otp" in path:
            return "auth.otp"
        return "auth"
    if "/admin" in path:
        return "admin"
    if "/users" in path:
        return "users"

    return "public"