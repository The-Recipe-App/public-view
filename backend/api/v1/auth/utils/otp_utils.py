# api/v1/auth/otp_utils.py

import secrets
import hashlib
import os
import json
import tempfile
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from utilities.common.common_utility import debug_print


# OTP policy tunables
OTP_TTL = 300
RESEND_COOLDOWN = 30
BLOCK_DURATION = 60 * 60 * 2
MAX_OTP_ATTEMPTS = 3
MAX_RESEND_BEFORE_BLOCK = 3
MAX_BLOCKS_BEFORE_BLACKLIST = 3


# ============================================================
# Shared File-Based Store (Cross-Platform, Multi-Worker Safe)
# ============================================================

STORE_FILE = os.path.join(tempfile.gettempdir(), "shared_otp_store.json")
LOCK_FILE = STORE_FILE + ".lock"


# ─────────────────────────────
# Cross-platform locking
# ─────────────────────────────

if sys.platform == "win32":
    import msvcrt

    def _lock(file):
        msvcrt.locking(file.fileno(), msvcrt.LK_LOCK, 1)

    def _unlock(file):
        msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock(file):
        fcntl.flock(file, fcntl.LOCK_EX)

    def _unlock(file):
        fcntl.flock(file, fcntl.LOCK_UN)


# ─────────────────────────────
# Internal helpers
# ─────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_ts() -> int:
    return int(_now().timestamp())


def _otp_key(challenge_id: str, email: Optional[str]) -> str:
    if email:
        return f"{challenge_id}:{email.lower()}"
    return challenge_id


def _verified_key(challenge_id: str, email: str) -> str:
    return f"verified:{challenge_id}:{email.lower()}"


def _read_store() -> Dict[str, Any]:
    if not os.path.exists(STORE_FILE):
        return {}

    try:
        with open(STORE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_store(data: Dict[str, Any]):
    tmp = STORE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, STORE_FILE)


def _with_lock(operation):
    os.makedirs(os.path.dirname(STORE_FILE), exist_ok=True)

    with open(LOCK_FILE, "a+") as lockf:
        _lock(lockf)
        try:
            store = _read_store()
            result = operation(store)
            _write_store(store)
            return result
        finally:
            _unlock(lockf)


def _cleanup_expired(store: Dict[str, Any]):
    now = _now_ts()

    expired = [
        k for k, v in store.items()
        if isinstance(v, dict) and v.get("expires_at", 0) <= now
    ]

    for k in expired:
        del store[k]


# ─────────────────────────────
# Core helpers
# ─────────────────────────────

def generate_otp(length: int = 6) -> str:
    n = secrets.randbelow(10**length)
    return str(n).zfill(length)


def make_challenge_id(fingerprint: Optional[str], ip: str) -> str:
    base = (fingerprint or "") + "|" + ip + "|" + secrets.token_hex(16)
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


# ─────────────────────────────
# OTP lifecycle
# ─────────────────────────────

async def save_otp(
    challenge_id: str,
    otp_code: str,
    device_hash: str,
    ip: str,
    user_agent: str,
    email: str = None,
    save_without_email: bool = False,
):
    key = _otp_key(challenge_id, None if save_without_email else email)

    def op(store):
        _cleanup_expired(store)

        store[key] = {
            # store HASH, not plaintext
            "code_hash": hashlib.sha256(otp_code.encode()).hexdigest(),
            "created_at": _now_ts(),
            "expires_at": _now_ts() + OTP_TTL,
            "attempts": 0,
            "resend_count": 0,
            "blocks": 0,
            "last_sent_at": _now_ts(),
            "email": email,
            "device_hash": device_hash,
            "ip": ip,
            "user_agent": user_agent,
        }
        debug_print(f"Saved OTP for {key}. Values: {store[key]}", color="green")

    _with_lock(op)


async def load_otp(challenge_id: str, email: str = None):
    key = _otp_key(challenge_id, email)

    def op(store):
        _cleanup_expired(store)
        return store.get(key)

    return _with_lock(op)


async def increment_attempt(challenge_id: str, email: str = None) -> int:
    key = _otp_key(challenge_id, email)

    def op(store):
        _cleanup_expired(store)
        data = store.get(key)
        if not data:
            return 0
        data["attempts"] += 1
        return data["attempts"]

    return _with_lock(op)


async def increment_resend(challenge_id: str, email: str) -> int:
    key = _otp_key(challenge_id, email)

    def op(store):
        _cleanup_expired(store)
        data = store.get(key)
        if not data:
            return 0
        data["resend_count"] += 1
        data["last_sent_at"] = _now_ts()
        return data["resend_count"]

    return _with_lock(op)


async def mark_verified(challenge_id: str, email: str = None):
    key = _verified_key(challenge_id, email)

    def op(store):
        _cleanup_expired(store)
        store[key] = {
            "expires_at": _now_ts() + 24 * 3600
        }

    _with_lock(op)


async def is_verified(challenge_id: str, email: str) -> bool:
    key = _verified_key(challenge_id, email)

    def op(store):
        _cleanup_expired(store)
        return key in store

    return _with_lock(op)


async def delete_otp(challenge_id: str, email: str | None = None):
    key = _otp_key(challenge_id, email)

    def op(store):
        store.pop(key, None)

    _with_lock(op)
