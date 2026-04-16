# api/v1/recipes/schemas.py
#
# Revision notes:
#
#  1.  RESPONSE MODELS ADDED — every endpoint previously returned a raw
#      dict. Without response_model FastAPI:
#        - Does not validate outbound data (a leaked internal field is
#          never caught until a client notices it)
#        - Generates no output schema in the OpenAPI doc — API consumers
#          have no contract to code against
#        - Cannot strip fields that are present on the ORM object but
#          should not be in the response (e.g. secret_hash on an identity
#          object accidentally passed through)
#
#      All response shapes are now declared here as Pydantic models.
#      Routers import and use them via response_model=.
#
#  2.  DUPLICATE SecurityOut CLASS REMOVED — profile/schemas.py declared
#      SecurityOut twice with different shapes. The second definition
#      (lower in the file) silently shadowed the first. Canonical version
#      kept here with all fields.

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Shared primitives ─────────────────────────────────────────────────────────

class OkResponse(BaseModel):
    ok: bool = True


class OkIdResponse(BaseModel):
    ok: bool = True
    id: int


# ── Ingredients / Steps ───────────────────────────────────────────────────────

class IngredientIn(BaseModel):
    name:        str  = Field(..., min_length=1)
    is_animal:   bool = False
    is_allergen: bool = False


class IngredientOut(BaseModel):
    id:          int
    name:        str
    is_animal:   bool
    is_allergen: bool


class StepIn(BaseModel):
    step_number:       int           = Field(..., ge=1)
    instruction:       str           = Field(..., min_length=1)
    technique:         Optional[str] = None
    estimated_minutes: Optional[int] = 0


class StepOut(BaseModel):
    step_number:       int
    instruction:       str
    technique:         Optional[str]
    estimated_minutes: Optional[int]


# ── Media ─────────────────────────────────────────────────────────────────────

class MediaIn(BaseModel):
    url:        str
    media_type: str
    position:   int = 0


class MediaOut(BaseModel):
    images: List[str]
    videos: List[str]


# ── Recipe create / fork / edit inputs ───────────────────────────────────────

class CreateRecipeReq(BaseModel):
    title:       str              = Field(..., min_length=3)
    body:        Optional[str]    = None
    ingredients: List[IngredientIn] = Field(default_factory=list)
    steps:       List[StepIn]
    license_id:  Optional[int]   = None
    is_draft:    bool             = True
    media:       List[MediaIn]    = Field(default_factory=list)


class ForkRecipeReq(BaseModel):
    title:      Optional[str] = None
    license_id: Optional[int] = None
    is_draft:   bool          = True


class EditRecipeReq(BaseModel):
    title:       Optional[str]              = None
    body:        Optional[str]              = None
    ingredients: Optional[List[IngredientIn]] = None
    steps:       Optional[List[StepIn]]    = None
    media:       Optional[List[MediaIn]]   = None


# ── Recipe responses ──────────────────────────────────────────────────────────

class RecipeCreateOut(BaseModel):
    ok:        bool
    recipe_id: int


class ReportOut(BaseModel):
    id:          int
    reason:      str
    details:     Optional[str]
    reporter_id: int
    created_at:  datetime


class LineageOut(BaseModel):
    root_recipe_id: Optional[int] = None
    depth:          Optional[int] = None


class RecipeDetailOut(BaseModel):
    id:              int
    title:           str
    body:            Optional[str]
    author_id:       int
    author_name:     str
    parent_id:       Optional[int]
    is_draft:        bool
    created_at:      datetime
    media:           MediaOut
    likes_count:     int
    views_count:     int
    forks_count:     int
    shares_count:    int
    bookmarks_count: int
    comments_count:  int
    ingredients:     List[IngredientOut]
    steps:           List[StepOut]

    # lineage
    root_recipe_id:  Optional[int]  = None
    depth:           Optional[int]  = None

    # report metadata (always present)
    reports_count:        int  = 0
    is_reported:          bool = False
    viewer_reported:      bool = False
    viewer_report_reason: Optional[str] = None

    # moderator-only (absent for regular users)
    recent_reports: Optional[List[ReportOut]] = None


class RecipeDetailResponse(BaseModel):
    ok:     bool
    recipe: RecipeDetailOut


# ── Feed ──────────────────────────────────────────────────────────────────────

class RecipeListItem(BaseModel):
    id:              int
    title:           str
    author_id:       int
    likes_count:     int
    views_count:     int
    shares_count:    int
    bookmarks_count: int
    created_at:      datetime


class PaginationOut(BaseModel):
    page:        int
    page_size:   int
    total:       int
    total_pages: int
    has_next:    bool
    has_prev:    bool


class FeedListResponse(BaseModel):
    items:      List[Dict[str, Any]]   # rich dicts from _serialize_recipe()
    pagination: PaginationOut
    sort:       str
    q:          Optional[str] = None


class RecommendationItem(BaseModel):
    id:        int
    title:     str
    author_id: int
    media:     Dict[str, Any]
    stats:     Dict[str, int]


class RecommendationsResponse(BaseModel):
    recipe_id:       Optional[int]
    count:           int
    recommendations: List[RecommendationItem]


class TrendingPreviewItem(BaseModel):
    id:        int
    title:     str
    author_id: int
    likes:     int
    views:     int
    image_url: Optional[str]
    score:     float


class TrendingPreviewResponse(BaseModel):
    items: List[TrendingPreviewItem]


# ── Voting / reactions ────────────────────────────────────────────────────────

class VoteReq(BaseModel):
    value: int = Field(..., description="Vote value must be +1 or -1")


class VoteResponse(BaseModel):
    ok:      bool
    applied: bool


class BookmarkResponse(BaseModel):
    ok:         bool
    bookmarked: bool


class ShareCreateReq(BaseModel):
    via:               Optional[str] = None
    share_link_token:  Optional[str] = None


class ShareResponse(BaseModel):
    ok:       bool
    share_id: int


class TrackViewResponse(BaseModel):
    ok: bool


# ── Comments ──────────────────────────────────────────────────────────────────

class CommentCreateReq(BaseModel):
    content:   str           = Field(..., min_length=1)
    parent_id: Optional[int] = None


class CommentOut(BaseModel):
    id:          int
    author_id:   int
    author_name: Optional[str]
    content:     str
    created_at:  datetime
    parent_id:   Optional[int]
    likes_count: int


class CommentCreateResponse(BaseModel):
    ok:         bool
    comment_id: int


# ── Reports ───────────────────────────────────────────────────────────────────

class ReportRecipeReq(BaseModel):
    reason:  str           = Field(..., min_length=3)
    details: Optional[str] = None


class ReportResponse(BaseModel):
    ok:       bool
    reported: bool


# ── Publish ───────────────────────────────────────────────────────────────────

class PublishResponse(BaseModel):
    ok:        bool
    published: bool


# ── Admin ─────────────────────────────────────────────────────────────────────

class LockResponse(BaseModel):
    ok:     bool
    locked: bool


class RecomputeCountersResponse(BaseModel):
    ok:        bool
    likes:     int
    views:     int
    shares:    int
    bookmarks: int


# ── Auth ──────────────────────────────────────────────────────────────────────

class MeResponse(BaseModel):
    id:         int
    username:   str
    reputation: int
    plan:       str
    avatar_url: Optional[str]
    is_admin:   bool


class LoginChallengeResponse(BaseModel):
    ok:           bool = False
    challenge:    str
    challenge_id: str
    masked_email: str
    expires_in:   int


class LoginSuccessResponse(BaseModel):
    ok: bool = True


class OtpRequestResponse(BaseModel):
    ok:              bool
    challenge_id:    str
    resend_cooldown: int
    expires_in:      int


class RegisterResponse(BaseModel):
    ok:                  bool
    activation_required: bool
    activation_sent:     bool


class ActivateResponse(BaseModel):
    ok:       bool
    username: str


# ── Profile / devices / passkeys ─────────────────────────────────────────────

class DeviceOut(BaseModel):
    id:            int
    user_agent:    str
    first_seen_at: datetime
    last_seen_at:  datetime
    is_trusted:    bool
    is_current:    bool


class PasskeyOut(BaseModel):
    id:           str
    name:         str
    created_at:   datetime
    last_used_at: Optional[datetime]


class BadgeOut(BaseModel):
    code:       str
    title:      str
    icon:       str
    awarded_at: datetime


class ReputationOut(BaseModel):
    score:              int
    level:              str
    next_level:         Optional[str]
    current_threshold:  int
    next_threshold:     Optional[int]
    progress_pct:       float
    can_vote:           bool
    can_moderate:       bool
    can_lock:           bool


class SecurityOut(BaseModel):
    """
    FIX #2 — canonical SecurityOut. Duplicate definition removed from
    profile/schemas.py (the second definition there shadowed the first).
    """
    email:        str
    is_banned:    bool
    plan:         str
    can_vote:     bool
    can_moderate: bool
    identities:   List[Dict[str, Any]]
    devices:      List[DeviceOut]
    passkeys:     List[PasskeyOut]