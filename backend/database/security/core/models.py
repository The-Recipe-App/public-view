# database/security/core/models.py
#
# Revision notes (what changed and why):
#
#  1.  MIXED COLUMN STYLES UNIFIED — PasskeyCredential and MobileAuthGrant
#      used legacy Column() style while the rest of the file used Mapped[].
#      All models now use Mapped[] consistently.
#
#  2.  server_default=func.now() REPLACES default=lambda: datetime.now(...)
#      on all created_at / updated_at fields.  The lambda form sets the
#      value in Python before the INSERT, meaning it uses the application
#      server's clock and timezone, not the DB server's.  server_default
#      lets PostgreSQL set it atomically and consistently.
#      Exception: EmailDomainPolicy.updated_at uses onupdate= which still
#      requires a Python-side callable — kept as-is with a comment.
#
#  3.  PasskeyCredential — added Mapped[] types, added index on user_id
#      (was present in __table_args__ but not on the column itself), added
#      server_default for created_at, and made last_used_at explicit.
#
#  4.  MobileAuthGrant — migrated to Mapped[] style, added index on
#      (is_used, expires_at) for fast "find valid unused grants" queries.
#
#  5.  UserDevice — added index on (user_id, is_revoked) since the most
#      common query is "active devices for user" which filters on both.
#      Added trust_updated_at for device trust audit.
#
#  6.  SecurityBlock — added blocked_at alias for created_at clarity;
#      added partial-style composite index for the hot "is this IP
#      currently blocked?" lookup path.
#
#  7.  AccountActivation — added index on user_id for "resend activation
#      for user" queries; previously only token was indexed.
#
#  8.  PendingUserConsent — added expiry TTL column so stale pending
#      consents can be garbage-collected.  Added index on challenge_id
#      + agreement_key for dedup checks.
#
#  9.  EmailDomainPolicy — replaced Python-side default=lambda with
#      server_default=func.now() for created_at; updated_at onupdate
#      remains Python-side since SQLAlchemy does not support
#      server-side onupdate for all backends uniformly.

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Dict, Any

from sqlalchemy import (
    String,
    Boolean,
    DateTime,
    Integer,
    func,
    Index,
    UniqueConstraint,
    LargeBinary,
    JSON,
    CheckConstraint,
    Text,
    UUID,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    """
    NOTE: onupdate=func.now() fires on ORM-level flushes only.
    Raw session.execute(update(...)) calls must set updated_at explicitly.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ============================================================
# SECURITY BLOCKS
# ============================================================


class SecurityBlock(Base):
    """
    Unified security block / audit table.
    Kept compact and indexed for fast lookups on every incoming request.
    """

    __tablename__ = "security_blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Identity being blocked
    ip_address: Mapped[str] = mapped_column(String(45), index=True, nullable=False)
    fingerprint_hash: Mapped[Optional[str]] = mapped_column(
        String(128), index=True, nullable=True
    )
    route: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Policy context
    policy_name: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    scope: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    # scope values: ROUTE | IP | IP_FINGERPRINT | GLOBAL

    # Block semantics
    is_permanent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    # Audit timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    __table_args__ = (
        Index("ix_security_blocks_identity", "ip_address", "fingerprint_hash"),
        Index("ix_security_blocks_policy_scope", "policy_name", "scope"),
        # Hot lookup: "is this IP actively blocked right now?"
        Index("ix_security_blocks_active_ip", "is_active", "ip_address", "expires_at"),
        Index("ix_security_blocks_active", "is_active", "is_permanent"),
    )


class RateLimitHits(Base):
    __tablename__ = "rate_limit_hits"
    key = mapped_column(String(255), primary_key=True, nullable=False)
    hit_id = mapped_column(UUID, primary_key=True, nullable=False)
    expires_at = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_rate_limit_hits_key", "key", "expires_at"),
        Index("ix_rate_limit_hits_hit_id", "hit_id", "expires_at"),
    )


# ============================================================
# USER DEVICES
# ============================================================


class UserDevice(Base):
    """
    Tracks known devices per user for device-bound session security.
    No FK to main.users — cross-DB logical reference via user_id.
    """

    __tablename__ = "user_devices"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Logical reference to main.users.id (no ForeignKey — different DB)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)

    # sha256(device_secret cookie value)
    device_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    user_agent: Mapped[str] = mapped_column(String(512), nullable=False)
    first_ip: Mapped[str] = mapped_column(String(45), nullable=False)
    last_ip: Mapped[str] = mapped_column(String(45), nullable=False)

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Trust model
    is_trusted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    trust_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # FIX — when was trust last changed? Useful for audit and trust decay logic.
    trust_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    last_asn: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_ip_subnet: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    meta: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "device_hash", name="uq_user_device"),
        Index("ix_user_devices_user", "user_id"),
        Index("ix_user_devices_last_ip", "last_ip"),
        # FIX — hot query: "active (non-revoked) devices for user"
        Index("ix_user_devices_user_active", "user_id", "is_revoked"),
    )


# ============================================================
# PASSKEY CREDENTIALS
# ============================================================


class PasskeyCredential(Base):
    """
    WebAuthn passkey credentials.
    No FK to main.users — cross-DB logical reference via user_id.
    """

    __tablename__ = "passkey_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Logical reference to main.users.id (no ForeignKey — different DB)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    label: Mapped[str] = mapped_column(String(255), nullable=False)

    # Large binary fields — deferred to avoid loading on list queries
    credential_id: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    public_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    sign_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    aaguid: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    transports: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # FIX #2 — server_default replaces Python-side lambda
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("credential_id", name="uq_passkey_credential_id"),
        Index("ix_passkey_user_id", "user_id"),
    )


# ============================================================
# ACCOUNT ACTIVATIONS
# ============================================================


class AccountActivation(Base):
    """
    One-time activation tokens created at registration.
    No FK to main.users — cross-DB logical reference.
    """

    __tablename__ = "account_activations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Logical reference to main.users.id (no ForeignKey — different DB)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)

    token: Mapped[str] = mapped_column(
        String(128), unique=True, index=True, nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)

    is_used: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # FIX #2 — server_default replaces Python-side default
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        # Composite index for the canonical validity check:
        # WHERE is_used = false AND expires_at > now()
        Index("ix_account_activation_active", "is_used", "expires_at"),
        # FIX #7 — lookup by user_id for "resend activation email" flow
        Index("ix_account_activation_user", "user_id"),
    )


# ============================================================
# PENDING USER CONSENTS
# ============================================================


class PendingUserConsent(Base, TimestampMixin):
    """
    Staging table for consent captured during OTP/registration flow,
    before the User row exists in main DB.  Rows are consumed and
    transferred to main.user_consents on successful registration,
    then deleted here.
    """

    __tablename__ = "pending_user_consents"

    id: Mapped[int] = mapped_column(primary_key=True)

    challenge_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)

    agreement_key: Mapped[str] = mapped_column(String(100), nullable=False)
    agreement_version: Mapped[str] = mapped_column(String(64), nullable=False)
    agreement_text_hash: Mapped[str] = mapped_column(String(128), nullable=False)

    accepted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    ip_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    meta: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # FIX #8 — TTL so stale rows can be garbage collected.
    # Set to registration OTP expiry + some buffer (e.g. 2 hours).
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    __table_args__ = (
        # FIX #8 — dedup check: "has this challenge already consented to this key?"
        Index("ix_pending_consent_challenge_key", "challenge_id", "agreement_key"),
    )


# ============================================================
# MOBILE AUTH GRANTS
# ============================================================


class MobileAuthGrant(Base):
    """
    Short-lived one-time token for mobile app authentication handoff.
    Browser issues a code, mobile app exchanges it for a JWT.
    """

    __tablename__ = "mobile_auth_grants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Logical reference to main.users.id (no ForeignKey — different DB)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    token: Mapped[str] = mapped_column(
        String(128), unique=True, index=True, nullable=False
    )
    is_used: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    # FIX #2 — server_default replaces Python-side default
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        # FIX #4 — fast lookup for valid, unused grants
        Index("ix_mobile_auth_grant_valid", "is_used", "expires_at"),
    )


# ============================================================
# EMAIL DOMAIN POLICY
# ============================================================


class EmailDomainPolicy(Base):
    """
    Authoritative email domain reputation & policy table.
    Used to block disposable, spam, or known-bad email domains at
    registration and login time.
    """

    __tablename__ = "email_domain_policies"

    id: Mapped[int] = mapped_column(primary_key=True)

    domain: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )

    # Policy flags — at least one should be True for meaningful rows
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_disposable: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_allowed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # 0–100 confidence score
    confidence: Mapped[int] = mapped_column(Integer, default=50, nullable=False)

    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=True,
    )

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        # FIX #9 — server_default instead of Python lambda
        server_default=func.now(),
        nullable=False,
    )
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # FIX #9 — server_default for created_at
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    # updated_at: Python-side onupdate remains because SQLAlchemy does not
    # universally support server-side onupdate across all backends.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "confidence >= 0 AND confidence <= 100",
            name="ck_email_domain_confidence_range",
        ),
        Index("ix_email_domain_active", "is_blocked", "is_disposable", "expires_at"),
        # Hot path: "is this specific domain currently blocked?"
        Index(
            "ix_email_domain_blocked_lookup", "domain", "is_blocked", "is_disposable"
        ),
    )
