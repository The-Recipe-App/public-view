from fastapi import HTTPException, status


# ─────────────────────────────
# Generic auth failures
# ─────────────────────────────

def auth_failed():
    """Used for login failures (do NOT leak info)"""
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
    )


# ─────────────────────────────
# Registration-specific errors
# ─────────────────────────────

def register_failed_duplicate():
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="User with this email already exists.",
    )


def register_failed_password_too_short(min_len: int):
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Password must be at least {min_len} characters long.",
    )


def register_failed_password_too_long(max_len: int):
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Password must not exceed {max_len} characters.",
    )

def register_failed_username_taken():
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Username is already taken.",
    )

def register_failed_username_invalid():
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid username.",
    )


def register_failed_password_weak():
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Password must contain at least one uppercase letter, one lowercase letter, one number, and one special character.",
    )


def register_failed_invalid_email():
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid email address.",
    )


# ─────────────────────────────
# Account state errors
# ─────────────────────────────

def account_banned():
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="This account has been disabled.",
    )


# ─────────────────────────────
# Rate limiting
# ─────────────────────────────

def rate_limited():
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many attempts. Try again later.",
    )
