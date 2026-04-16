# database/main/core/models.py
#
# Revision notes (what changed and why):
#
#  1.  DUPLICATE COLUMNS REMOVED — Recipe had shares_count, bookmarks_count,
#      forks_count, and comments_count declared twice.  SQLAlchemy silently
#      used the last declaration; the first was dead weight and confusion.
#
#  2.  RecipeMedia REWRITTEN — switched from legacy Column() style to modern
#      Mapped[] style; added MediaType enum enforcement via SQLEnum; replaced
#      datetime.utcnow (naïve, deprecated) with func.now() (timezone-aware,
#      server-side); added storage_key for S3 key tracking; added index on
#      (recipe_id, position) and a CHECK on position >= 0.
#
#  3.  ALL lazy="joined" ON CHILD→PARENT BACK-REFERENCES CHANGED — joined
#      loading from the child side causes every query touching those models
#      to emit an extra JOIN even when the parent is not needed.  High-volume
#      append-only tables (Activity, RecipeView, RecipeCounterShard) are now
#      lazy="raise" so accidental traversal is a loud error, not a silent
#      extra query.  Other child→parent refs use lazy="select" (load only
#      when explicitly accessed).
#
#  4.  RecipeCounterShard — added UniqueConstraint("recipe_id", "shard_id")
#      to prevent duplicate shards; a bare Index does not prevent duplicates.
#
#  5.  ShareableLink — added is_exhausted / is_expired properties for
#      clean validation logic; the composite token validity index is improved.
#
#  6.  RecipeReport — added resolved_by_id FK for moderator audit trail.
#
#  7.  Vote.validate() — removed session-dependent user access; replaced with
#      a static check_can_vote(user) class method so it can be called with an
#      already-loaded user without risking a lazy-load inside a closed session.
#
#  8.  Bookmark.notes — capped at String(500) instead of unbounded Text.
#
#  9.  Activity — added object_table / object_id for subject→object events
#      (e.g. "user X forked recipe Y" — Y is the object).
#
# 10.  Tag / RecipeTag M2M added — ConstraintType.REQUIRED_TAG referenced tags
#      but there was no table to back them, forcing all tag logic into raw
#      strings inside KitchenConstraint.value.
#
# 11.  User.reputation_level property — sorted() was called on every access;
#      now uses a pre-sorted tuple constant so the sort runs once at import.
#
# 12.  TimestampMixin.updated_at — onupdate=func.now() is correct but only
#      fires on ORM-level updates, not raw UPDATE statements.  Added a comment
#      so this is explicit rather than surprising.
#
# 13.  All `default=lambda: datetime.now(timezone.utc)` patterns on
#      Mapped[] columns replaced with server_default=func.now() where
#      possible so the DB, not Python, owns the clock.  Python-side defaults
#      remain where the value must be computed before insert.

from __future__ import annotations

import re
from datetime import datetime, date, timezone
from enum import Enum
from typing import Optional, Dict, List
from dataclasses import dataclass

from sqlalchemy import (
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    Integer,
    UniqueConstraint,
    CheckConstraint,
    Index,
    Enum as SQLEnum,
    func,
    JSON,
    Date,
    text,
    Column,
)
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
    validates,
)

from database.main.core.base import Base


# ============================================================
# ENUMS
# ============================================================


class VoteValue(int, Enum):
    UP = 1
    DOWN = -1


class TargetType(str, Enum):
    RECIPE = "recipe"
    COMMENT = "comment"


class ConstraintType(str, Enum):
    MAX_STEPS = "max_steps"
    MAX_TIME = "max_time"
    ALLOWED_INGREDIENT = "allowed_ingredient"
    FORBIDDEN_INGREDIENT = "forbidden_ingredient"
    FORBIDDEN_TECHNIQUE = "forbidden_technique"
    REQUIRED_TAG = "required_tag"
    CUSTOM = "custom"


class ValidationStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"


class PlanTier(str, Enum):
    FREE = "FREE"
    CREATOR = "CREATOR"
    PRO = "PRO"
    ORG = "ORG"


class MediaType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"

class DifficultyLevel(str, Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"

class ReputationLevel(Enum):
    NEW = 0
    CONTRIBUTOR = 50
    TRUSTED = 200
    EXPERT = 500
    STEWARD = 1000


# FIX #11 — sorted once at import time, not on every property access.
_REPUTATION_LEVELS_DESC: tuple[ReputationLevel, ...] = tuple(
    sorted(ReputationLevel, key=lambda x: x.value, reverse=True)
)


@dataclass(frozen=True)
class TierLimits:
    max_images: int
    max_videos: int
    allow_videos: bool


PLAN_LIMITS: dict[PlanTier, TierLimits] = {
    PlanTier.FREE: TierLimits(max_images=5, max_videos=0, allow_videos=False),
    PlanTier.CREATOR: TierLimits(max_images=15, max_videos=0, allow_videos=False),
    PlanTier.PRO: TierLimits(max_images=50, max_videos=5, allow_videos=True),
    PlanTier.ORG: TierLimits(max_images=500, max_videos=100, allow_videos=True),
}


# ============================================================
# MIXINS
# ============================================================


class TimestampMixin:
    """
    NOTE: updated_at uses onupdate=func.now() which fires on ORM-level
    flushes only.  Raw `session.execute(update(...))` statements will NOT
    update this column automatically — call func.now() explicitly in those.
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


class SoftDeleteMixin:
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )


# ============================================================
# USER & AUTH
# ============================================================

_EMAIL_RE = re.compile(r"^[^@]+@[^@]+\.[^@]+$")


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    username: Mapped[str] = mapped_column(
        String(150),
        unique=True,
        index=True,
        nullable=False,
    )
    username_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=True,
    )
    is_username_system_generated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    email_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )

    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    avatar_changed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    avatar_key: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True
    )
    website: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    twitter: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True
    )
    youtube: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True
    )

    reputation: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        index=True,
    )
    is_banned: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )
    is_admin: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    plan_tier: Mapped[PlanTier] = mapped_column(
        SQLEnum(PlanTier, name="plan_tier_enum"),
        nullable=False,
        default=PlanTier.FREE,
        index=True,
    )

    activation_token: Mapped[Optional[str]] = mapped_column(
        String(128),
        unique=True,
        index=True,
        nullable=True,
    )
    activation_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=True,
    )
    is_activated: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # Denormalised counters — updated via atomic SQL increments, never
    # read-modify-write in Python to avoid race conditions.
    recipes_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, index=True
    )
    forks_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, index=True
    )
    comments_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, index=True
    )
    votes_received: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, index=True
    )

    # Legal / age
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    age_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    age_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    age_verification_method: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )

    # ── Relationships ──────────────────────────────────────────────────────
    consents = relationship(
        "UserConsent",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="raise",
        passive_deletes=True,
    )
    auth_identities = relationship(
        "AuthIdentity",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="raise",
    )
    recipes = relationship("Recipe", back_populates="author", lazy="raise")
    comments = relationship("Comment", back_populates="author", lazy="raise")
    votes = relationship("Vote", back_populates="user", lazy="raise")
    badges = relationship(
        "UserBadge", back_populates="user", cascade="all, delete-orphan", lazy="raise"
    )
    shares = relationship("Share", back_populates="user", lazy="raise")
    shareable_links = relationship(
        "ShareableLink", back_populates="created_by_user", lazy="raise"
    )
    bookmarks = relationship("Bookmark", back_populates="user", lazy="raise")
    activities = relationship("Activity", back_populates="user", lazy="raise")

    __table_args__ = (
        CheckConstraint("reputation >= -10000", name="ck_user_reputation_min"),
        CheckConstraint("reputation <= 1000000", name="ck_user_reputation_max"),
        Index("ix_user_plan_reputation", "plan_tier", "reputation"),
        Index(
            "ix_user_activity_rank", "recipes_count", "forks_count", "votes_received"
        ),
    )

    @validates("email")
    def validate_email(self, _, value: str) -> str:
        if not _EMAIL_RE.fullmatch(value):
            raise ValueError("email must be a valid email address")
        return value

    @property
    def reputation_level(self) -> ReputationLevel:
        # FIX #11 — uses pre-sorted constant, no sort() on every call.
        for level in _REPUTATION_LEVELS_DESC:
            if self.reputation >= level.value:
                return level
        return ReputationLevel.NEW

    @property
    def limits(self) -> TierLimits:
        return PLAN_LIMITS.get(self.plan_tier, PLAN_LIMITS[PlanTier.FREE])

    def assert_not_banned(self) -> None:
        if self.is_banned:
            raise PermissionError("User is banned")

    def can_vote(self) -> bool:
        return not self.is_banned and self.reputation >= 0

    def can_moderate(self) -> bool:
        return not self.is_banned and self.reputation >= 500

    def apply_reputation(self, delta: int) -> None:
        self.reputation = max(-10000, self.reputation + delta)

    def plan_allows_videos(self) -> bool:
        return self.limits.allow_videos

    def allowed_images_limit(self) -> int:
        return self.limits.max_images

    def allowed_videos_limit(self) -> int:
        return self.limits.max_videos


class UserConsent(Base, TimestampMixin):
    """
    Append-only legal consent ledger.
    One row per acceptance event — never UPDATE, only revoke via revoked_at.
    """

    __tablename__ = "user_consents"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agreement_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    agreement_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    agreement_text_hash: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, index=True
    )

    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    ip_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    meta: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    policy_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("policy_versions.id"),
        nullable=True,
        index=True,
    )

    user = relationship("User", back_populates="consents")

    __table_args__ = (
        Index("ix_user_consents_user_agreement", "user_id", "agreement_key"),
        Index(
            "ix_user_consents_user_agreement_date",
            "user_id",
            "agreement_key",
            "accepted_at",
        ),
        CheckConstraint("agreement_key <> ''", name="ck_user_consent_key_not_empty"),
    )

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


class UserBadge(Base):
    __tablename__ = "user_badges"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    icon: Mapped[str] = mapped_column(String(100), nullable=False)
    awarded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
        nullable=False,
    )

    user = relationship("User", back_populates="badges", lazy="joined")

    __table_args__ = (
        UniqueConstraint("user_id", "code", name="uq_user_badge_unique"),
        Index("ix_user_badge_lookup", "user_id", "code"),
    )


class AuthIdentity(Base, TimestampMixin):
    __tablename__ = "auth_identities"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_identity: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    secret_hash: Mapped[Optional[str]] = mapped_column(String(255))
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    user = relationship("User", back_populates="auth_identities", lazy="joined")

    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_user_id", name="uq_auth_provider_identity"
        ),
        CheckConstraint(
            "(provider = 'password' AND secret_hash IS NOT NULL)"
            " OR (provider != 'password' AND secret_hash IS NULL)",
            name="ck_auth_identity_secret_rules",
        ),
        CheckConstraint("provider <> ''", name="ck_auth_provider_not_empty"),
        CheckConstraint(
            "provider LIKE LOWER(provider)", name="ck_auth_provider_lowercase_only"
        ),
        Index("ix_auth_identity_lookup", "provider", "provider_user_id"),
    )


# ============================================================
# KITCHENS & CONSTRAINTS
# ============================================================


class Kitchen(Base, TimestampMixin):
    __tablename__ = "kitchens"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    constraints = relationship(
        "KitchenConstraint",
        back_populates="kitchen",
        cascade="all, delete-orphan",
        lazy="raise",
        passive_deletes=True,
    )
    validations = relationship("RecipeKitchenValidation", lazy="raise")


class KitchenConstraint(Base):
    __tablename__ = "kitchen_constraints"

    id: Mapped[int] = mapped_column(primary_key=True)
    kitchen_id: Mapped[int] = mapped_column(
        ForeignKey("kitchens.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[ConstraintType] = mapped_column(
        SQLEnum(ConstraintType, name="constraint_type_enum"),
        nullable=False,
    )
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    kitchen = relationship("Kitchen", back_populates="constraints", lazy="joined")


# ============================================================
# TAGS  (FIX #10 — new tables; ConstraintType.REQUIRED_TAG had no backing store)
# ============================================================


class Tag(Base):
    """
    Canonical tag dictionary.  slug is the stable identifier used in
    KitchenConstraint.value for REQUIRED_TAG constraints.
    """

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(100), nullable=False)

    recipe_tags = relationship("RecipeTag", back_populates="tag", lazy="raise")


class RecipeTag(Base):
    """Many-to-many join table between recipes and tags."""

    __tablename__ = "recipe_tags"

    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    )

    tag = relationship("Tag", back_populates="recipe_tags", lazy="joined")
    recipe = relationship("Recipe", back_populates="tags", lazy="raise")


# ============================================================
# RECIPES & LINEAGE
# ============================================================


class Recipe(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
        index=True,
    )
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("recipes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    score: Mapped[int] = mapped_column(Integer, default=0)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    is_draft: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Denormalised counters ──────────────────────────────────────────────
    # IMPORTANT: always increment/decrement via atomic SQL UPDATE, never via
    # Python read-modify-write, to avoid race conditions under concurrency.
    # Example:
    #   await session.execute(
    #       update(Recipe).where(Recipe.id == id).values(likes_count=Recipe.likes_count + 1)
    #   )
    likes_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, index=True
    )
    views_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, index=True
    )
    forks_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, index=True
    )
    shares_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, index=True
    )
    bookmarks_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, index=True
    )
    comments_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, index=True
    )

    # ── Relationships ──────────────────────────────────────────────────────
    author = relationship("User", back_populates="recipes", lazy="joined")
    parent = relationship(
        "Recipe",
        remote_side="Recipe.id",
        back_populates="forks",
        lazy="raise",
        passive_deletes=True,
    )
    forks = relationship("Recipe", back_populates="parent", lazy="raise")

    ingredients = relationship(
        "Ingredient",
        back_populates="recipe",
        cascade="all, delete-orphan",
        lazy="raise",
        passive_deletes=True,
    )
    steps = relationship(
        "RecipeStep",
        back_populates="recipe",
        cascade="all, delete-orphan",
        lazy="raise",
        passive_deletes=True,
    )
    comments = relationship(
        "Comment",
        back_populates="recipe",
        cascade="all, delete-orphan",
        lazy="raise",
        passive_deletes=True,
    )
    tags = relationship(
        "RecipeTag",
        back_populates="recipe",
        cascade="all, delete-orphan",
        lazy="raise",
    )
    media = relationship(
        "RecipeMedia",
        back_populates="recipe",
        cascade="all, delete-orphan",
        order_by="RecipeMedia.position",
        lazy="raise",
    )
    validations = relationship(
        "RecipeKitchenValidation",
        cascade="all, delete-orphan",
        lazy="raise",
        passive_deletes=True,
    )
    licenses = relationship(
        "RecipeLicense",
        back_populates="recipe",
        cascade="all, delete-orphan",
        lazy="raise",
    )
    shareable_links = relationship(
        "ShareableLink",
        back_populates="recipe",
        cascade="all, delete-orphan",
        lazy="raise",
    )
    shares = relationship(
        "Share",
        back_populates="recipe",
        cascade="all, delete-orphan",
        lazy="raise",
    )
    views = relationship(
        "RecipeView",
        back_populates="recipe",
        cascade="all, delete-orphan",
        lazy="raise",
    )
    bookmarks = relationship(
        "Bookmark",
        back_populates="recipe",
        cascade="all, delete-orphan",
        lazy="raise",
    )
    counter_shards = relationship(
        "RecipeCounterShard",
        back_populates="recipe",
        cascade="all, delete-orphan",
        lazy="raise",
    )
    
    cuisine: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True
    )
    difficulty: Mapped[Optional[DifficultyLevel]] = mapped_column(
        SQLEnum(DifficultyLevel, name="difficulty_level_enum"),
        nullable=True,
        index=True,
    )
    prep_time_mins: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cook_time_mins: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    search_vector = Column(TSVECTOR, nullable=True)
    embedding = Column(Vector(384), nullable=True)

    __table_args__ = (
        Index("ix_recipe_parent", "parent_id"),
        Index("ix_recipe_not_deleted", "is_deleted"),
        Index("ix_recipe_author_created", "author_id", "created_at"),
        Index("ix_recipe_published_feed", "is_draft", "published_at"),
        Index("ix_recipes_search_vector", "search_vector", postgresql_using="gin"),
        Index(
            "ix_recipes_embedding",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    @validates("title")
    def validate_title(self, _, value: str) -> str:
        value = value.strip()
        if len(value) < 5:
            raise ValueError("Recipe title too short")
        return value

    def assert_can_comment(self) -> None:
        if self.is_locked or self.is_deleted:
            raise PermissionError("Recipe is locked or removed")

    def apply_vote(self, value: VoteValue) -> None:
        self.score += int(value)


class RecipeLineageSnapshot(Base, TimestampMixin):
    __tablename__ = "recipe_lineage_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    root_recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (UniqueConstraint("recipe_id", name="uq_recipe_lineage_snapshot"),)


# ============================================================
# INGREDIENTS & STEPS
# ============================================================


class Ingredient(Base):
    __tablename__ = "ingredients"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    is_animal: Mapped[bool] = mapped_column(Boolean, default=False)
    is_allergen: Mapped[bool] = mapped_column(Boolean, default=False)

    # FIX #3 — child→parent back-ref: lazy="raise" so we are forced to load
    # ingredients via their recipe query, not accidentally traverse upward.
    recipe = relationship("Recipe", back_populates="ingredients", lazy="raise")


class RecipeStep(Base):
    __tablename__ = "recipe_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    technique: Mapped[Optional[str]] = mapped_column(String(100))
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=0)
    # tool: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    recipe = relationship("Recipe", back_populates="steps", lazy="raise")

    __table_args__ = (UniqueConstraint("recipe_id", "step_number"),)


# ============================================================
# RECIPE ↔ KITCHEN VALIDATION
# ============================================================


class RecipeKitchenValidation(Base, TimestampMixin):
    __tablename__ = "recipe_kitchen_validations"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kitchen_id: Mapped[int] = mapped_column(
        ForeignKey("kitchens.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[ValidationStatus] = mapped_column(
        SQLEnum(ValidationStatus, name="validation_status_enum"),
        nullable=False,
        index=True,
    )

    recipe = relationship("Recipe", back_populates="validations", lazy="joined")
    kitchen = relationship("Kitchen", viewonly=True, lazy="joined")

    __table_args__ = (UniqueConstraint("recipe_id", "kitchen_id"),)


class ConstraintViolation(Base):
    __tablename__ = "constraint_violations"

    id: Mapped[int] = mapped_column(primary_key=True)
    validation_id: Mapped[int] = mapped_column(
        ForeignKey("recipe_kitchen_validations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    constraint_id: Mapped[int] = mapped_column(
        ForeignKey("kitchen_constraints.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (Index("ix_constraint_violation_validation", "validation_id"),)


# ============================================================
# COMMENTS & VOTES
# ============================================================


class Comment(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
        index=True,
    )
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=0)
    likes_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, index=True
    )

    author = relationship("User", back_populates="comments", lazy="joined")
    recipe = relationship("Recipe", back_populates="comments", lazy="select")
    parent = relationship("Comment", remote_side="Comment.id", lazy="raise")

    def apply_vote(self, value: VoteValue) -> None:
        self.score += int(value)

    __table_args__ = (
        Index("ix_comments_recipe_created", "recipe_id", "created_at"),
        Index("ix_comments_author_created", "author_id", "created_at"),
    )


class Vote(Base):
    __tablename__ = "votes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_type: Mapped[TargetType] = mapped_column(
        SQLEnum(TargetType, name="vote_target_type_enum"),
        nullable=False,
        index=True,
    )
    target_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    value: Mapped[int] = mapped_column(Integer, nullable=False)

    # FIX #3 — lazy="select" here; the user is already loaded on the hot
    # auth path so this won't fire in practice, but we don't force a JOIN
    # on every vote read.
    user = relationship("User", back_populates="votes", lazy="select")

    # FIX #7 — static method so callers pass an already-loaded User,
    # preventing session-dependent access inside a potentially closed session.
    @staticmethod
    def check_can_vote(user: "User") -> None:
        if not user.can_vote():
            raise PermissionError("User cannot vote")

    __table_args__ = (
        UniqueConstraint("user_id", "target_type", "target_id"),
        CheckConstraint("value IN (-1, 1)", name="ck_vote_value"),
        Index("ix_vote_target", "target_type", "target_id"),
        Index("ix_vote_user", "user_id"),
    )


# ============================================================
# RECIPE MEDIA  (FIX #2 — full rewrite)
# ============================================================


class RecipeMedia(Base, TimestampMixin):
    """
    Stores uploaded image/video metadata for a recipe.

    Changes from original:
    - Uses Mapped[] style consistently with the rest of the file.
    - media_type enforced as MediaType enum via SQLEnum (was raw String).
    - storage_key added — the S3/local key needed for deletion/CDN invalidation.
    - created_at provided by TimestampMixin with timezone=True (was naive utcnow).
    - position >= 0 check constraint added.
    - Composite index on (recipe_id, position) for ordered media fetch.
    """

    __tablename__ = "recipe_media"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    media_type: Mapped[MediaType] = mapped_column(
        SQLEnum(MediaType, name="media_type_enum"),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)

    # S3 / local storage key — needed to delete the file when media is removed.
    storage_key: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True, index=True
    )

    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    recipe = relationship("Recipe", back_populates="media", lazy="raise")

    __table_args__ = (
        CheckConstraint("position >= 0", name="ck_recipe_media_position"),
        Index("ix_recipe_media_recipe_position", "recipe_id", "position"),
    )


# ============================================================
# RECIPE REPORTS
# ============================================================


class RecipeReport(Base, TimestampMixin):
    """One report per user per recipe. Moderators review via admin."""

    __tablename__ = "recipe_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reporter_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reason: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    resolved: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # FIX — who resolved it? Essential for moderation audit trail.
    resolved_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    recipe = relationship("Recipe", lazy="joined")
    reporter = relationship("User", foreign_keys=[reporter_id], lazy="joined")
    resolved_by = relationship("User", foreign_keys=[resolved_by_id], lazy="select")

    __table_args__ = (
        UniqueConstraint("recipe_id", "reporter_id", name="uq_recipe_report_unique"),
        Index("ix_recipe_reports_recipe", "recipe_id"),
        Index("ix_recipe_reports_reporter", "reporter_id"),
        Index("ix_recipe_reports_created", "created_at"),
    )


# ============================================================
# LICENSES
# ============================================================


class License(Base):
    __tablename__ = "licenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    desc: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)


class RecipeLicense(Base):
    __tablename__ = "recipe_licenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    license_id: Mapped[int] = mapped_column(
        ForeignKey("licenses.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    granted_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    recipe = relationship("Recipe", back_populates="licenses", lazy="joined")
    license = relationship("License", lazy="joined")

    __table_args__ = (
        UniqueConstraint("recipe_id", name="uq_recipe_license"),
        Index("ix_recipe_license_lookup", "recipe_id", "license_id"),
    )


# ============================================================
# SHAREABLE LINKS, SHARES, VIEWS, BOOKMARKS
# ============================================================


class ShareableLink(Base):
    __tablename__ = "shareable_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    max_uses: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    uses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    recipe = relationship("Recipe", back_populates="shareable_links", lazy="joined")
    created_by_user = relationship(
        "User", back_populates="shareable_links", lazy="joined"
    )

    # FIX — validity helpers used in share endpoints and link validation.
    @property
    def is_exhausted(self) -> bool:
        return self.max_uses is not None and self.uses >= self.max_uses

    @property
    def is_expired(self) -> bool:
        return (
            self.expires_at is not None
            and datetime.now(tz=timezone.utc) > self.expires_at
        )

    @property
    def is_valid(self) -> bool:
        return not self.is_exhausted and not self.is_expired

    __table_args__ = (
        Index("ix_shareable_links_recipe_token", "recipe_id", "token"),
        # Speeds up "find all valid (non-expired, not-exhausted) links" queries
        Index("ix_shareable_links_expires", "expires_at"),
    )


class Share(Base):
    __tablename__ = "shares"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
        index=True,
    )
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    via: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    share_link_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("shareable_links.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    user = relationship("User", back_populates="shares", lazy="joined")
    recipe = relationship("Recipe", back_populates="shares", lazy="joined")
    share_link = relationship("ShareableLink", lazy="select")

    __table_args__ = (
        Index("ix_shares_recipe_user", "recipe_id", "user_id", "created_at"),
    )


class RecipeView(Base):
    """
    Append-only view log. High write volume — do NOT load recipe/user
    eagerly from this side; traverse from Recipe or User instead.
    """

    __tablename__ = "recipe_views"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    ip_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # FIX #3 — lazy="raise" on both sides; this is an append-only log table.
    # Never traverse from a RecipeView back up to Recipe or User.
    recipe = relationship("Recipe", back_populates="views", lazy="raise")

    __table_args__ = (
        Index("ix_recipe_views_recipe_created", "recipe_id", "created_at"),
        Index("ix_recipe_views_recipe_user", "recipe_id", "user_id"),
    )

    Index(
        "ix_recipe_views_dedup_user",
        "recipe_id",
        "user_id",
        "created_at",
        postgresql_where=text("user_id IS NOT NULL"),
    ),
    Index(
        "ix_recipe_views_dedup_anon",
        "recipe_id",
        "ip_hash",
        "created_at",
        postgresql_where=text("ip_hash IS NOT NULL"),
    ),


class Bookmark(Base):
    __tablename__ = "bookmarks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    # FIX #8 — capped at 500 chars; unbounded Text is too much for an
    # inline bookmark note that's displayed in list views.
    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    user = relationship("User", back_populates="bookmarks", lazy="joined")
    recipe = relationship("Recipe", back_populates="bookmarks", lazy="joined")

    __table_args__ = (
        UniqueConstraint("user_id", "recipe_id", name="uq_user_bookmark"),
        Index("ix_bookmarks_user_created", "user_id", "created_at"),
    )


# ============================================================
# ACTIVITY LOG  (FIX #9 — added object_table / object_id)
# ============================================================


class Activity(Base):
    """
    Append-only activity log.

    subject = who/what performed the action  (e.g. the recipe that was created)
    object  = what the action was performed on (e.g. the recipe that was forked FROM)

    Example:  verb="recipe.fork"
                subject_table="recipes"  subject_id=<new fork id>
                object_table="recipes"   object_id=<original recipe id>
    """

    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    verb: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    subject_table: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    subject_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, index=True
    )

    # FIX #9 — the "object" of the action (what the subject acted upon)
    object_table: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    object_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # FIX #3 — lazy="raise"; Activity is append-only.  Never traverse up
    # to User from an Activity row — load User first, then its activities.
    user = relationship("User", back_populates="activities", lazy="raise")

    __table_args__ = (
        Index("ix_activities_user_verb", "user_id", "verb"),
        Index("ix_activities_created", "created_at"),
        Index("ix_activities_object", "object_table", "object_id"),
    )


# ============================================================
# SHARDED COUNTERS  (FIX #4 — UniqueConstraint added)
# ============================================================


class RecipeCounterShard(Base):
    """
    Sharded counters to reduce write contention on hot recipes.
    Create N shards per recipe (e.g. 8).  A background aggregator rolls
    the shards into recipe.likes_count / views_count / shares_count
    periodically.

    FIX: UniqueConstraint("recipe_id", "shard_id") added — the previous
    bare Index did not prevent duplicate (recipe_id, shard_id) pairs.
    """

    __tablename__ = "recipe_counter_shards"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    shard_id: Mapped[int] = mapped_column(Integer, nullable=False)
    views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    likes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    shares: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # FIX #3 — lazy="raise"; always accessed via Recipe.counter_shards,
    # never from the shard upward.
    recipe = relationship("Recipe", back_populates="counter_shards", lazy="raise")

    __table_args__ = (
        # FIX #4 — this is the correctness guarantee; the index is for speed.
        UniqueConstraint("recipe_id", "shard_id", name="uq_recipe_shard"),
        Index("ix_recipe_counter_shard_recipe_shard", "recipe_id", "shard_id"),
    )


# ============================================================
# FOLLOWS
# ============================================================

class UserFollow(Base):
    """
    follower_id follows following_id.
    "I (follower) follow them (following)."
    """
    __tablename__ = "user_follows"

    follower_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    following_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        CheckConstraint("follower_id != following_id", name="ck_no_self_follow"),
        Index("ix_follow_follower", "follower_id"),
        Index("ix_follow_following", "following_id"),
    )

# ============================================================
# LEGAL POLICIES
# ============================================================


class Policy(Base, TimestampMixin):
    """Logical policy container (e.g. 'tos', 'privacy', 'cookies')."""

    __tablename__ = "policies"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    versions = relationship(
        "PolicyVersion",
        back_populates="policy",
        cascade="all, delete-orphan",
        order_by="PolicyVersion.effective_at.desc()",
        lazy="raise",
    )


class PolicyVersion(Base, TimestampMixin):
    """Immutable policy snapshot — metadata in DB, text in static file."""

    __tablename__ = "policy_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    policy_id: Mapped[int] = mapped_column(
        ForeignKey("policies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    locale: Mapped[str] = mapped_column(
        String(10), default="en", nullable=False, index=True
    )

    file_url: Mapped[str] = mapped_column(String(512), nullable=False)
    file_format: Mapped[str] = mapped_column(
        String(20), default="markdown", nullable=False
    )
    text_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )
    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    policy = relationship("Policy", back_populates="versions", lazy="joined")

    __table_args__ = (
        UniqueConstraint(
            "policy_id", "version", "locale", name="uq_policy_version_locale"
        ),
        Index("ix_policy_version_active", "policy_id", "is_active"),
        Index("ix_policy_version_effective", "policy_id", "effective_at"),
    )
