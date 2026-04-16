# utilities/common/retries.py

import logging
import asyncpg
import sqlalchemy.exc

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception,
    before_sleep_log,
)

logger = logging.getLogger("db.retry")


# -------------------------------------------------------------------
# Retry policy
# -------------------------------------------------------------------
# IMPORTANT RULE:
# - Retry ONLY when a retry has a *higher chance* of succeeding.
# - NEVER retry on pool exhaustion / timeouts.
# -------------------------------------------------------------------


RETRYABLE_DB_ERRORS = (
    # asyncpg connection-level failures
    asyncpg.CannotConnectNowError,
    asyncpg.ConnectionDoesNotExistError,
    asyncpg.TooManyConnectionsError,

    # SQLAlchemy wraps some driver disconnects as OperationalError
    sqlalchemy.exc.OperationalError,
)


def is_retryable_db_error(exc: Exception) -> bool:
    """
    Decide whether a DB exception is safe to retry.

    NEVER retry:
      - SQLAlchemy TimeoutError (connection pool exhausted)
      - Programming / integrity errors
    """

    # Pool exhaustion / checkout timeout → FAIL FAST
    if isinstance(exc, sqlalchemy.exc.TimeoutError):
        return False

    # Explicitly retry only known transient connection errors
    return isinstance(exc, RETRYABLE_DB_ERRORS)


# -------------------------------------------------------------------
# Public decorator (used as @retry_db)
# -------------------------------------------------------------------

retry_db = retry(
    reraise=True,
    stop=stop_after_attempt(2),  # 1 retry is enough; avoids latency amplification
    wait=wait_exponential_jitter(
        initial=0.2,              # fast retry
        max=1.5,                  # never sleep long
    ),
    retry=retry_if_exception(is_retryable_db_error),
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
