import os
import sys
import json
import logging
from pathlib import Path
from functools import lru_cache
from logging.handlers import RotatingFileHandler

# ---------------------------
# Root Resolver
# ---------------------------

CACHE_FILE = Path(__file__).parent / ".file_root_cache.json"

def _load_disk_cache() -> dict:
    if not CACHE_FILE.exists():
        return {}
    try:
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_disk_cache(cache: dict) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)

@lru_cache(maxsize=64)
def get_file_root_path(file_name: str = "app.py", start_path: str | None = None) -> str:
    start_path = Path(start_path or Path(__file__).resolve().parents[3])

    disk_cache = _load_disk_cache()
    cached = disk_cache.get(file_name)
    if cached:
        p = Path(cached)
        if p.exists() and (start_path == p or start_path in p.parents):
            return str(p)

    for root, _, files in os.walk(start_path):
        if file_name in files:
            found = Path(root) / file_name
            disk_cache[file_name] = str(found)
            _save_disk_cache(disk_cache)
            return str(found)

    raise FileNotFoundError(f"{file_name} not found starting from {start_path}")

def resolve_path(*relative_path: str) -> str:
    return str(Path(get_file_root_path()).parent.joinpath(*relative_path))

# ---------------------------
# Ultra-Fast ANSI System
# ---------------------------

COLOR_DIRECTORY = {
    "black": "\033[30m", "red": "\033[31m", "green": "\033[32m", "yellow": "\033[33m",
    "blue": "\033[34m", "magenta": "\033[35m", "cyan": "\033[36m", "white": "\033[37m",
    "bright_black": "\033[90m", "bright_red": "\033[91m", "bright_green": "\033[92m",
    "bright_yellow": "\033[93m", "bright_blue": "\033[94m", "bright_magenta": "\033[95m",
    "bright_cyan": "\033[96m", "bright_white": "\033[97m",
    "bg_black": "\033[40m", "bg_red": "\033[41m", "bg_green": "\033[42m",
    "bg_yellow": "\033[43m", "bg_blue": "\033[44m", "bg_magenta": "\033[45m",
    "bg_cyan": "\033[46m", "bg_white": "\033[47m",
    "bg_bright_black": "\033[100m", "bg_bright_red": "\033[101m",
    "bg_bright_green": "\033[102m", "bg_bright_yellow": "\033[103m",
    "bg_bright_blue": "\033[104m", "bg_bright_magenta": "\033[105m",
    "bg_bright_cyan": "\033[106m", "bg_bright_white": "\033[107m",
    "bold": "\033[1m", "dim": "\033[2m", "italic": "\033[3m",
    "underline": "\033[4m", "blink": "\033[5m", "reverse": "\033[7m",
    "hidden": "\033[8m", "strike": "\033[9m", "reset": "\033[0m",
}

RESET = COLOR_DIRECTORY["reset"]

# Precompile replacements once
_ANSI_REPLACEMENTS = {f"{{{k}}}": v for k, v in COLOR_DIRECTORY.items()}

# ---------------------------
# Debug Flags
# ---------------------------

DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"
DEBUG_TO_FILE = os.getenv("DEBUG_TO_FILE", "false").lower() == "true"

# ---------------------------
# File Logger (Hot Path Ready)
# ---------------------------

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "debug.log"

_logger: logging.Logger | None = None

def _init_file_logger() -> logging.Logger:
    """
    Initialize and return a dedicated file logger used when DEBUG_TO_FILE is enabled.
    Safe to call multiple times.
    """
    global _logger
    if _logger:
        return _logger

    logger = logging.getLogger("DEBUG")
    logger.setLevel(logging.DEBUG)

    handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )

    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False

    _logger = logger
    return logger

# initialize file logger eagerly if requested
if DEBUG_TO_FILE:
    _init_file_logger()

# ---------------------------
# Lightning-Fast Debug Print
# ---------------------------

def debug_print(
    message,
    *args,
    color: str = "white",
    tag: str = "DEBUG",
    logger: logging.Logger | None = None,
    level: str = "debug",
    exc_info: bool = False,
):
    """
    Ultra-fast debug printer.

    Behaviour:
      - If DEBUG_MODE is True -> prints to console (with ANSI).
      - If DEBUG_TO_FILE is True or a logger is supplied -> emits to that logger.
      - If DEBUG_MODE is False and neither DEBUG_TO_FILE nor logger are provided -> no-op.

    Accepts formatting args like stdlib logging: debug_print("user %s created", username)
    """
    # Fast path: nothing to do
    if not DEBUG_MODE and not DEBUG_TO_FILE and logger is None:
        return

    # Fast caller lookup (cheap)
    try:
        frame = sys._getframe(1)
        location = f"{os.path.basename(frame.f_code.co_filename)}:{frame.f_lineno}"
    except Exception:
        location = "Unknown:??"

    # Resolve console color (if any)
    base = COLOR_DIRECTORY.get(color.lower(), RESET) if isinstance(color, str) else RESET

    # Convert message template and apply inline {color} replacements for console output
    msg_template = str(message)

    # For console printing: if args provided, try to format using % operator (like logging)
    if args:
        try:
            formatted_msg = msg_template % args
        except Exception:
            # fallback: join reprs to avoid crashing
            try:
                formatted_msg = msg_template + " " + " ".join(map(str, args))
            except Exception:
                formatted_msg = msg_template
    else:
        formatted_msg = msg_template

    # Inline replacement — precompiled dict keeps this fast
    for key, ansi in _ANSI_REPLACEMENTS.items():
        formatted_msg = formatted_msg.replace(key, ansi)

    final = f"[{tag}] [{location}] {formatted_msg}"

    # Console output only in DEBUG_MODE (preserve previous behaviour)
    if DEBUG_MODE:
        try:
            print(f"{base}{final}{RESET}")
        except Exception:
            pass

    # Logging to file / provided logger
    target_logger = None
    if logger is not None:
        target_logger = logger
    elif DEBUG_TO_FILE:
        # Ensure file logger is initialized
        target_logger = _init_file_logger()

    if target_logger:
        # Pass original template and args to logger so it can do lazy formatting:
        # e.g. _logger.debug("user %s created", user)
        log_func = getattr(target_logger, level.lower(), target_logger.debug)
        try:
            if args:
                log_func(msg_template, *args, exc_info=exc_info)
            else:
                log_func(msg_template, exc_info=exc_info)
        except Exception:
            # If that fails, try logging the already-formatted final string
            try:
                target_logger.debug(final)
            except Exception:
                pass

# ---------------------------
# Fast Structured Print
# ---------------------------

def custom_print(
    message,
    *args,
    color: str = "yellow",
    type_: str | None = None,
    caller_info: bool = True,
    logger: logging.Logger | None = None,
    level: str | None = None,
):
    """
    Structured print helper.

    Behaviour:
      - Always prints to stdout (keeps original behavior).
      - Optionally logs to provided logger (if logger is given).
      - `type_` can be 'error', 'warning', 'info', 'success' to change color & prefix.
      - Accepts formatting args like stdlib logging: custom_print("hello %s", name)
    """
    base = COLOR_DIRECTORY.get(color.lower(), RESET)

    if type_:
        type_colors = {
            "error": "red", "warning": "yellow", "info": "blue", "success": "green"
        }
        base = COLOR_DIRECTORY.get(type_colors.get(type_, color), RESET)
        # prefix will be added before formatting
        prefix = f"[{type_.upper()}] "
    else:
        prefix = ""

    if caller_info:
        try:
            f = sys._getframe(1)
            caller = f"[{os.path.basename(f.f_code.co_filename)}:{f.f_lineno}] "
        except Exception:
            caller = ""
    else:
        caller = ""

    msg_template = f"{caller}{prefix}{message}"

    # Format for console
    if args:
        try:
            formatted_msg = msg_template % args
        except Exception:
            try:
                formatted_msg = msg_template + " " + " ".join(map(str, args))
            except Exception:
                formatted_msg = msg_template
    else:
        formatted_msg = msg_template

    # Apply ANSI replacements
    for key, ansi in _ANSI_REPLACEMENTS.items():
        formatted_msg = formatted_msg.replace(key, ansi)

    # Console output (original behaviour always printed)
    try:
        print(f"{base}{formatted_msg}{RESET}")
    except Exception:
        pass

    # Optional logging to provided logger
    if logger:
        chosen_level = (level or type_ or "info").lower()
        log_func = getattr(logger, chosen_level, logger.info)
        try:
            if args:
                log_func(msg_template, *args)
            else:
                log_func(msg_template)
        except Exception:
            try:
                logger.info(formatted_msg)
            except Exception:
                pass

# ---------------------------
# Boot message (keeps original UX)
# ---------------------------

custom_print("Debug mode is " + ("enabled" if DEBUG_MODE else "disabled"), type_="info")
