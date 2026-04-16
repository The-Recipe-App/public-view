from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from passlib.context import CryptContext
import re

# ─────────────────────────────
# Config (use env vars in prod)
# ─────────────────────────────
SECRET_KEY = "CHANGE_ME"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60*24  # 1 day

PASSWORD_MIN_LEN = 8
PASSWORD_MAX_LEN = 64  # bcrypt-safe

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

from utilities.common.common_utility import debug_print

def debug_password(password: str, label: str = "password"):
    try:
        byte_len = len(password.encode("utf-8"))
        char_len = len(password)

        if char_len >= 4:
            masked = f"{password[:2]}***{password[-2:]}"
        else:
            masked = "***"

        debug_print(
            (
                f"{label} debug -> "
                f"chars={char_len}, "
                f"bytes={byte_len}, "
                f"repr={repr(password)}, "
                f"masked='{masked}'"
            ),
            color="bright_yellow",
        )
    except Exception as e:
        debug_print(f"{label} debug failed: {e}", color="red")


def validate_password_strength(password: str):
    if not re.search(r"[A-Z]", password):
        from api.v1.auth.errors import register_failed_password_weak
        register_failed_password_weak()
    if not re.search(r"[a-z]", password):
        register_failed_password_weak()
    if not re.search(r"\d", password):
        register_failed_password_weak()
    if not re.search(r"[^\w\s]", password):
        register_failed_password_weak()

def validate_password_length(password: str):
    if len(password) < PASSWORD_MIN_LEN:
        from api.v1.auth.errors import register_failed_password_too_short
        register_failed_password_too_short(PASSWORD_MIN_LEN)

    if len(password) > PASSWORD_MAX_LEN:
        from api.v1.auth.errors import register_failed_password_too_long
        register_failed_password_too_long(PASSWORD_MAX_LEN)
    
    validate_password_strength(password)

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


# ─────────────────────────────
# Create
# ─────────────────────────────
def create_access_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "type": "access",
        "exp": datetime.now(timezone.utc)
        + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# ─────────────────────────────
# Decode / Verify
# ─────────────────────────────
def decode_access_token(token: str) -> int:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as e:
        raise PermissionError(f"Invalid token: {str(e)}")

    if payload.get("type") != "access":
        raise PermissionError("Invalid token type")

    sub = payload.get("sub")
    if not sub:
        raise PermissionError("Token missing subject")

    return int(sub)
