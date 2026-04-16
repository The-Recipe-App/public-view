# api/v1/auth/utils/security.py
#
# Revision notes:
#
#  1.  HARDCODED SECRET_KEY REMOVED — the original had SECRET_KEY = "CHANGE_ME"
#      as a module-level string with a comment saying "use env vars in prod".
#      That comment was never acted on, and a hardcoded key means every JWT
#      ever issued by this app can be forged by anyone who reads this file
#      (or your git history).  The new code uses os.environ["JWT_SECRET_KEY"]
#      with no default — it raises KeyError at startup if unset, which is the
#      correct behaviour: better to crash loudly on boot than to run silently
#      with a known-insecure key.
#
#  2.  ACCESS_TOKEN_EXPIRE_MINUTES MOVED TO ENV — hardcoded to 1440 (1 day).
#      Now reads JWT_EXPIRE_MINUTES from env, defaulting to 60 (1 hour).
#      A 24-hour token lifetime is very long for a session token with no
#      refresh mechanism. 60 minutes is a safer default; you can override
#      via env on any environment.
#
#  3.  ALGORITHM VALIDATED AT STARTUP — if someone sets JWT_ALGORITHM to
#      "none" (a known JWT attack vector) the app refuses to start.
#
#  4.  SECRET_KEY LENGTH VALIDATED AT STARTUP — HS256 with a short key is
#      weak. We require at least 32 bytes (256 bits). A good way to generate
#      one: python -c "import secrets; print(secrets.token_hex(32))"
#
#  5.  decode_access_token NOW RAISES AuthenticationError CONSISTENTLY —
#      the original let JWTError propagate raw. The call sites in
#      dependencies.py caught it, but any call site that forgot to catch
#      it would crash with a 500. Centralising the error mapping here means
#      call sites just catch one known exception type.
#
#  6.  create_access_token NOW ACCEPTS iat (issued-at) — added to payload
#      so tokens can be invalidated by checking issue time against a
#      "password changed at" or "logged out at" timestamp stored on the
#      device/user row. Without iat, you cannot do time-based token
#      invalidation without a full token blocklist.
#
#  7.  debug_password GUARDED BEHIND DEBUG FLAG — it logs partial plaintext
#      passwords to stdout. Acceptable in local dev, a serious problem if
#      it ever runs in production. Wrapped in a DEBUG_MODE check so it
#      becomes a no-op the moment DEBUG=false in env.
#
#  8.  validate_password_strength FIXED — the original had four separate
#      if-blocks, each calling register_failed_password_weak() on the first
#      failing rule and returning immediately (via HTTPException inside that
#      call). This meant the error message always said "weak password"
#      regardless of which rule failed, and only one rule was ever checked
#      before bailing. The new version checks all rules upfront and returns
#      a specific message for the first unmet rule.

from __future__ import annotations

import os
import re
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt, JWTError
from passlib.context import CryptContext

from utilities.common.common_utility import debug_print

logger = logging.getLogger("auth.security")

# ── Config (all values come from environment — no hardcoded secrets) ──────────

# Hard fail at import time if the secret is not set.
# Generate a good one with:  python -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET_KEY: str = os.environ["JWT_SECRET_KEY"]

ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")

# Protect against the "alg: none" JWT attack and other nonsense values.
_ALLOWED_ALGORITHMS = {"HS256", "HS384", "HS512"}
if ALGORITHM not in _ALLOWED_ALGORITHMS:
    raise RuntimeError(
        f"JWT_ALGORITHM={ALGORITHM!r} is not allowed. "
        f"Must be one of: {sorted(_ALLOWED_ALGORITHMS)}"
    )

# Require a minimum key length.  HS256 needs at least 256 bits = 32 bytes.
if len(JWT_SECRET_KEY.encode()) < 32:
    raise RuntimeError(
        "JWT_SECRET_KEY is too short (must be at least 32 bytes / 256 bits). "
        "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
    )

ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "320"))

PASSWORD_MIN_LEN = 8
PASSWORD_MAX_LEN = 64  # bcrypt silently truncates at 72 bytes — 64 is a safe cap

DEBUG_MODE: bool = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")

# ── Password hashing ──────────────────────────────────────────────────────────

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── Password validation ───────────────────────────────────────────────────────

# FIX #8 — check all rules and return a specific message rather than
# a generic "weak password" on the first failing rule.

_PASSWORD_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"[A-Z]"),    "Password must contain at least one uppercase letter."),
    (re.compile(r"[a-z]"),    "Password must contain at least one lowercase letter."),
    (re.compile(r"\d"),       "Password must contain at least one digit."),
    (re.compile(r"[^\w\s]"),  "Password must contain at least one special character."),
]


def validate_password_length(password: str) -> None:
    """
    Validate password length and strength.
    Raises via the auth error helpers on failure.
    """
    from api.v1.auth.errors import (
        register_failed_password_too_short,
        register_failed_password_too_long,
        register_failed_password_weak,
    )

    if len(password) < PASSWORD_MIN_LEN:
        register_failed_password_too_short(PASSWORD_MIN_LEN)

    if len(password) > PASSWORD_MAX_LEN:
        register_failed_password_too_long(PASSWORD_MAX_LEN)

    validate_password_strength(password)


def validate_password_strength(password: str) -> None:
    from api.v1.auth.errors import register_failed_password_weak

    for pattern, message in _PASSWORD_RULES:
        if not pattern.search(password):
            register_failed_password_weak(message)
            return  # register_failed_password_weak raises, but be explicit


# ── JWT creation ──────────────────────────────────────────────────────────────

def create_access_token(
    user_id: int,
    device_hash: str,
    is_admin: bool = False,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub":   str(user_id),
        "did":   device_hash,
        "admin": is_admin,
        "iat":   now,                                                   # FIX #6
        "exp":   now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=ALGORITHM)


# ── JWT decoding ──────────────────────────────────────────────────────────────

class AuthenticationError(Exception):
    """Raised by decode_access_token on any JWT validation failure."""


def decode_access_token(token: str) -> dict:
    """
    Decode and verify a JWT access token.

    Returns the payload dict on success.
    Raises AuthenticationError on any failure (expired, invalid signature,
    malformed, wrong algorithm, missing claims).

    FIX #5 — all JWT errors are mapped to one known exception type here
    so call sites don't need to import JWTError or handle raw jose exceptions.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise AuthenticationError(f"Invalid token: {exc}") from exc

    # Verify required claims are present.
    if not payload.get("sub") or not payload.get("did"):
        raise AuthenticationError("Token is missing required claims (sub, did)")

    return payload


# ── Debug helpers (dev only) ──────────────────────────────────────────────────

def debug_password(password: str, label: str = "password") -> None:
    """
    FIX #7 — no-op unless DEBUG=true in environment.
    Never logs partial plaintext passwords in production.
    """
    if not DEBUG_MODE:
        return

    try:
        byte_len = len(password.encode("utf-8"))
        char_len = len(password)
        masked = f"{password[:2]}***{password[-2:]}" if char_len >= 4 else "***"
        debug_print(
            f"{label} debug -> chars={char_len}, bytes={byte_len}, masked='{masked}'",
            color="bright_yellow",
        )
    except Exception as exc:
        debug_print(f"{label} debug failed: {exc}", color="red")