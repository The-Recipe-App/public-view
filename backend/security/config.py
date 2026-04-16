# security/config.py
import os

class FirewallConfig:
    """
    Infrastructure-level configuration only.
    All rate limits and escalation thresholds are policy-driven.
    """
    DB_URL = os.getenv("SECURITY_DB_URL")

    # Absolute safety caps (to prevent misconfigured policies from killing the server)
    MAX_RATE_LIMIT = 5000          # hard upper bound per window
    MAX_WINDOW_SECONDS = 3600      # 1 hour max rolling window
    MAX_ESCALATION_COUNT = 100     # absolute ceiling for escalate_after

    # Fingerprint / identity settings (future use)
    FINGERPRINT_HEADER = "X-Client-Fingerprint"
