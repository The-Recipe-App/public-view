from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Request,
    status,
)
from typing import Optional, List

from sqlalchemy import (
    select,
    bindparam,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, aliased

from pydantic import AnyUrl
from datetime import datetime, timedelta, timezone
import re
import asyncio

from database.main.core.models import (
    User,
    ReputationLevel,
    AuthIdentity,
    Recipe,
    Comment,
    Bookmark,
    Activity,
    Share,
    UserBadge,
)
from database.security.core.models import UserDevice, PasskeyCredential

from database.main.core.session import get_async_session, AsyncSessionLocal
from database.security.core.session import get_security_session

from api.v1.auth.utils.device import (
    hash_device,
    DEVICE_COOKIE,
)

from api.v1.auth.utils.dependencies import (
    get_current_user,
    get_current_user_optional,
    revoke_all_other_devices,
    revoke_device_by_id,
)


from api.v1.profile.schemas import (
    ProfileUpdateSchema,
    BadgeOut,
    ReputationOut,
    SecurityOut,
)

from api.v1.media.media_helpers import handle_avatar_upload

from app.username_index import username_index


# ============================================================
# Router
# ============================================================

profile_router = APIRouter(prefix="/profile", tags=["profile"])


# ============================================================
# Constants / Validation
# ============================================================

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,30}$")
USERNAME_COOLDOWN_DAYS = 7


# ============================================================
# Precompiled Query Params
# ============================================================

UID = bindparam("uid")
UNAME = bindparam("uname")
DH = bindparam("dh")
DID = bindparam("did")


# ============================================================
# Precompiled Statements (Hot Path)
# ============================================================

# Public profile lookup
PUBLIC_USER_LOOKUP = (
    select(User)
    .where(User.username == UNAME)
    .limit(1)
)

# Username uniqueness check
USERNAME_EXISTS_STMT = (
    select(User.id)
    .where(User.username == UNAME)
    .limit(1)
)

# Badges eager load
USER_BADGES_LOOKUP = (
    select(User)
    .options(selectinload(User.badges))
    .where(User.username == UNAME)
    .limit(1)
)

# Auth identities lookup
IDENTITIES_LOOKUP = (
    select(AuthIdentity)
    .where(AuthIdentity.user_id == UID)
)

# Devices lookup
DEVICES_LOOKUP = (
    select(UserDevice)
    .where(
        UserDevice.user_id == UID,
        UserDevice.is_revoked.is_(False),
    )
    .order_by(UserDevice.last_seen_at.desc())
)

# Passkeys lookup
PASSKEY_LOOKUP = (
    select(PasskeyCredential)
    .where(PasskeyCredential.user_id == UID)
    .order_by(PasskeyCredential.created_at.desc())
)

# Current device lookup
CURRENT_DEVICE_LOOKUP = (
    select(UserDevice)
    .where(
        UserDevice.user_id == UID,
        UserDevice.device_hash == DH,
        UserDevice.is_revoked.is_(False),
    )
    .limit(1)
)

# Activity queries
PUBLIC_RECIPES_ACTIVITY = (
    select(Recipe.title, Recipe.created_at)
    .where(
        Recipe.author_id == UID,
        Recipe.is_deleted.is_(False),
    )
    .order_by(Recipe.created_at.desc())
    .limit(10)
)

PUBLIC_COMMENTS_ACTIVITY = (
    select(Comment.content, Comment.created_at)
    .where(
        Comment.author_id == UID,
        Comment.is_deleted.is_(False),
    )
    .order_by(Comment.created_at.desc())
    .limit(10)
)

OWNER_DRAFT_ACTIVITY = (
    select(Recipe.title, Recipe.updated_at)
    .where(
        Recipe.author_id == UID,
        Recipe.is_deleted.is_(True),
    )
    .order_by(Recipe.updated_at.desc())
    .limit(10)
)


# ============================================================
# Utilities
# ============================================================

def http_error(code: int, msg: str):
    raise HTTPException(status_code=code, detail=msg)


async def ensure_unique_username(
    session: AsyncSession,
    username: str,
    exclude_user_id: int | None = None,
):
    exists = await session.scalar(
        USERNAME_EXISTS_STMT,
        {"uname": username},
    )

    if exists and exists != exclude_user_id:
        http_error(status.HTTP_409_CONFLICT, "Username already taken")


# ============================================================
# Profile Endpoints
# ============================================================

@profile_router.get("/me")
async def my_profile(user: User = Depends(get_current_user)):
    """
    Hot path: already loaded from auth dependency cache.
    """
    return {
        "id": user.id,
        "username": user.username,
        "avatar_url": user.avatar_url,
        "avatar_changed_at": user.avatar_changed_at,
        "bio": user.bio,
        "location": user.location,
        "website": user.website,
        "twitter": user.twitter,
        "youtube": user.youtube,
        "plan": user.plan_tier,
        "reputation": {
            "score": user.reputation,
            "level": user.reputation_level.name,
        },
        "stats": {
            "recipes": user.recipes_count,
            "forks": user.forks_count,
            "comments": user.comments_count,
            "votes_received": user.votes_received,
        },
        "created_at": user.created_at,
        "is_admin": user.is_admin,
    }


@profile_router.get("/{username}")
async def public_profile(
    username: str,
    session: AsyncSession = Depends(get_async_session),
):
    user = await session.scalar(
        PUBLIC_USER_LOOKUP,
        {"uname": username},
    )

    if not user:
        http_error(status.HTTP_404_NOT_FOUND, "User not found")

    return {
        "username": user.username,
        "avatar_url": user.avatar_url,
        "avatar_changed_at": user.avatar_changed_at,
        "bio": user.bio,
        "location": user.location,
        "website": user.website,
        "twitter": user.twitter,
        "youtube": user.youtube,
        "reputation": {
            "score": user.reputation,
            "level": user.reputation_level.name,
        },
        "stats": {
            "recipes": user.recipes_count,
            "forks": user.forks_count,
            "comments": user.comments_count,
            "votes_received": user.votes_received,
        },
        "created_at": user.created_at,
    }


# ============================================================
# Update Profile
# ============================================================

@profile_router.patch("/me")
async def update_profile(
    payload: ProfileUpdateSchema,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    if not payload.model_fields_set:
        http_error(status.HTTP_400_BAD_REQUEST, "No fields provided")

    old_username = user.username

    # Username update
    if payload.username and payload.username != user.username:
        if not USERNAME_RE.fullmatch(payload.username):
            http_error(status.HTTP_400_BAD_REQUEST, "Invalid username format")

        if user.username_updated_at:
            delta = datetime.now(timezone.utc) - user.username_updated_at
            if delta < timedelta(days=USERNAME_COOLDOWN_DAYS):
                http_error(status.HTTP_429_TOO_MANY_REQUESTS, f"You can only change your username once every {USERNAME_COOLDOWN_DAYS} days")

        await ensure_unique_username(session, payload.username, exclude_user_id=user.id)

        user.username = payload.username
        user.username_updated_at = datetime.now(timezone.utc)
        user.is_username_system_generated = False

    # Other fields
    for field in ("bio", "location", "website", "twitter", "youtube"):
        if field in payload.model_fields_set:
            val = getattr(payload, field)
            if isinstance(val, AnyUrl):
                val = str(val)
            setattr(user, field, val)

    session.add(user)
    await session.commit()

    # Update index after commit
    if payload.username and payload.username != old_username:
        username_index.add(user.username)
        username_index.remove(old_username)

    return {"ok": True}


# ============================================================
# Badges
# ============================================================

@profile_router.get("/{username}/badges", response_model=list[BadgeOut])
async def public_badges(
    username: str,
    session: AsyncSession = Depends(get_async_session),
):
    user = await session.scalar(
        USER_BADGES_LOOKUP,
        {"uname": username},
    )

    if not user:
        http_error(status.HTTP_404_NOT_FOUND, "User not found")

    return [
        {
            "code": b.code,
            "title": b.title,
            "icon": b.icon,
            "awarded_at": b.awarded_at,
        }
        for b in user.badges
    ]


@profile_router.get("/me/badges", response_model=list[BadgeOut])
async def my_badges(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    user = await session.scalar(
        USER_BADGES_LOOKUP,
        {"uname": user.username},
    )

    return [
        {
            "code": b.code,
            "title": b.title,
            "icon": b.icon,
            "awarded_at": b.awarded_at,
        }
        for b in user.badges
    ]


# ============================================================
# Reputation
# ============================================================

@profile_router.get("/me/reputation", response_model=ReputationOut)
async def reputation_power(user: User = Depends(get_current_user)):
    levels = sorted(ReputationLevel, key=lambda x: x.value)
    current = user.reputation_level

    next_level = next((lvl for lvl in levels if lvl.value > current.value), None)

    if not next_level:
        progress = 100.0
        next_threshold = None
    else:
        next_threshold = next_level.value
        progress = (
            (user.reputation - current.value)
            / (next_threshold - current.value)
        ) * 100

    return {
        "score": user.reputation,
        "level": current.name,
        "next_level": next_level.name if next_level else None,
        "current_threshold": current.value,
        "next_threshold": next_threshold,
        "progress_pct": round(progress, 2),
        "can_vote": user.can_vote(),
        "can_moderate": user.can_moderate(),
        "can_lock": user.can_moderate(),
    }


# ============================================================
# Security Info (Optimized)
# ============================================================

@profile_router.get("/me/security", response_model=SecurityOut)
async def security_info(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
    security_session: AsyncSession = Depends(get_security_session),
    request: Request = None,
):
    identities = (
        await session.scalars(
            IDENTITIES_LOOKUP,
            {"uid": user.id},
        )
    ).all()

    primary = next((i for i in identities if i.is_primary), None)

    devices = (
        await security_session.scalars(
            DEVICES_LOOKUP,
            {"uid": user.id},
        )
    ).all()

    passkeys = (
        await security_session.scalars(
            PASSKEY_LOOKUP,
            {"uid": user.id},
        )
    ).all()

    device_secret = request.cookies.get(DEVICE_COOKIE)
    current_hash = hash_device(device_secret) if device_secret else None

    current_device = None
    if current_hash:
        current_device = await security_session.scalar(
            CURRENT_DEVICE_LOOKUP,
            {"uid": user.id, "dh": current_hash},
        )

    return {
        "email": primary.user.email if primary else None,
        "is_banned": user.is_banned,
        "plan": user.plan_tier.name,
        "can_vote": user.can_vote(),
        "can_moderate": user.can_moderate(),
        "identities": [
            {"provider": i.provider_identity, "is_primary": i.is_primary, "type": "OAuth" if i.provider == "supabase" else "Password"}
            for i in identities
        ],
        "devices": [
            {
                "id": d.id,
                "user_agent": d.user_agent,
                "first_seen_at": d.first_seen_at,
                "last_seen_at": d.last_seen_at,
                "is_trusted": d.is_trusted,
                "is_current": d.device_hash == current_hash,
            }
            for d in devices
        ],
        "passkeys": [
            {
                "id": str(p.id),
                "name": p.label or "Passkey",
                "created_at": p.created_at,
                "last_used_at": p.last_used_at,
            }
            for p in passkeys
        ],
        "current_device_id": current_device.id if current_device else None,
    }


# ============================================================
# Avatar Upload
# ============================================================

@profile_router.post("/me/avatar")
async def upload_avatar(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    return await handle_avatar_upload(
        request=request,
        user=user,
        session=session,
        file=file,
    )


# ============================================================
# Public Activity (Compiled Queries)
# ============================================================

@profile_router.get("/{username}/activity")
async def public_activity(
    username: str,
    before: Optional[str] = None,
    session: AsyncSession = Depends(get_async_session),
    viewer: Optional[User] = Depends(get_current_user_optional),
):
    user = await session.scalar(
        select(User).where(User.username == username).limit(1)
    )
    if not user:
        http_error(status.HTTP_404_NOT_FOUND, "User not found")

    uid = user.id
    is_owner = viewer is not None and viewer.id == uid
    cursor = datetime.fromisoformat(before) if before else datetime.now(timezone.utc)

    Fork = aliased(Recipe, name="fork")

    # ── Build all statements ──────────────────────────────────────────────

    stmt_activity = (
        select(Activity)
        .where(Activity.user_id == uid, Activity.created_at < cursor)
        .order_by(Activity.created_at.desc())
        .limit(20)
    )

    stmt_published = (
        select(Recipe.id, Recipe.title, Recipe.published_at)
        .where(
            Recipe.author_id == uid,
            Recipe.is_draft.is_(False),
            Recipe.is_deleted.is_(False),
            Recipe.published_at < cursor,
        )
        .order_by(Recipe.published_at.desc())
        .limit(10)
    )

    stmt_forks = (
        select(Fork.id, Fork.title, Fork.created_at, Fork.parent_id)
        .where(
            Fork.parent_id.in_(
                select(Recipe.id).where(
                    Recipe.author_id == uid,
                    Recipe.is_deleted.is_(False),
                )
            ),
            Fork.author_id != uid,
            Fork.is_deleted.is_(False),
            Fork.created_at < cursor,
        )
        .order_by(Fork.created_at.desc())
        .limit(10)
    )

    stmt_comments = (
        select(Comment.id, Comment.content, Comment.created_at, Comment.recipe_id)
        .where(
            Comment.author_id == uid,
            Comment.is_deleted.is_(False),
            Comment.created_at < cursor,
        )
        .order_by(Comment.created_at.desc())
        .limit(10)
    ) if is_owner else (
        select(Comment.id, Comment.content, Comment.created_at, Comment.recipe_id)
        .join(Recipe, Recipe.id == Comment.recipe_id)
        .where(
            Recipe.author_id == uid,
            Comment.author_id != uid,
            Comment.is_deleted.is_(False),
            Comment.created_at < cursor,
        )
        .order_by(Comment.created_at.desc())
        .limit(10)
    )

    stmt_bookmarks = (
        select(Bookmark.id, Bookmark.created_at, Bookmark.recipe_id, Recipe.title)
        .join(Recipe, Recipe.id == Bookmark.recipe_id)
        .where(
            Bookmark.user_id == uid,
            Bookmark.created_at < cursor,
            Recipe.is_deleted.is_(False),
        )
        .order_by(Bookmark.created_at.desc())
        .limit(10)
    ) if is_owner else None

    stmt_shares = (
        select(Share.id, Share.created_at, Share.recipe_id, Share.via, Recipe.title)
        .join(Recipe, Recipe.id == Share.recipe_id)
        .where(
            Share.user_id == uid,
            Share.created_at < cursor,
            Recipe.is_deleted.is_(False),
        )
        .order_by(Share.created_at.desc())
        .limit(10)
    )

    stmt_badges = (
        select(UserBadge.code, UserBadge.title, UserBadge.icon, UserBadge.awarded_at)
        .where(UserBadge.user_id == uid, UserBadge.awarded_at < cursor)
        .order_by(UserBadge.awarded_at.desc())
        .limit(5)
    )

    stmt_drafts = (
        select(Recipe.id, Recipe.title, Recipe.updated_at)
        .where(
            Recipe.author_id == uid,
            Recipe.is_draft.is_(True),
            Recipe.is_deleted.is_(False),
            Recipe.updated_at < cursor,
        )
        .order_by(Recipe.updated_at.desc())
        .limit(10)
    ) if is_owner else None

    # ── Each query gets its own session — safe for asyncio.gather ────────

    async def _run(stmt):
        async with AsyncSessionLocal() as s:
            return await s.execute(stmt)

    async def _run_or_none(stmt):
        if stmt is None:
            return None
        return await _run(stmt)

    (
        activity_log_res,
        published_res,
        forks_received_res,
        comments_res,
        bookmarks_res,
        shares_res,
        badges_res,
        drafts_res,
    ) = await asyncio.gather(
        _run(stmt_activity),
        _run(stmt_published),
        _run(stmt_forks),
        _run(stmt_comments),
        _run_or_none(stmt_bookmarks),
        _run(stmt_shares),
        _run(stmt_badges),
        _run_or_none(stmt_drafts),
    )

    # ── Serialise ─────────────────────────────────────────────────────────

    items: list[dict] = []

    for row in activity_log_res.scalars():
        items.append({
            "type":      row.verb,
            "title":     _verb_label(row.verb, row.payload),
            "when":      row.created_at.isoformat(),
            "recipe_id": row.subject_id if row.subject_table == "recipes" else row.object_id,
            "metadata":  row.payload or {},
        })

    for recipe_id, title, published_at in published_res.all():
        items.append({
            "type":      "recipe_published",
            "title":     f"Published '{title}'",
            "when":      (published_at or cursor).isoformat(),
            "recipe_id": recipe_id,
            "metadata":  {},
        })

    for fork_id, fork_title, created_at, parent_id in forks_received_res.all():
        items.append({
            "type":      "fork_received",
            "title":     f"'{fork_title}' was forked from your recipe",
            "when":      created_at.isoformat(),
            "recipe_id": parent_id,
            "metadata":  {"fork_id": fork_id, "fork_title": fork_title},
        })

    for comment_id, content, created_at, recipe_id in comments_res.all():
        items.append({
            "type":      "comment" if is_owner else "comment_received",
            "title":     f"Commented: {content[:100]}{'…' if len(content) > 100 else ''}",
            "when":      created_at.isoformat(),
            "recipe_id": recipe_id,
            "metadata":  {"comment_id": comment_id},
        })

    if bookmarks_res is not None:
        for bm_id, created_at, recipe_id, recipe_title in bookmarks_res.all():
            items.append({
                "type":      "bookmark",
                "title":     f"Saved '{recipe_title}'",
                "when":      created_at.isoformat(),
                "recipe_id": recipe_id,
                "metadata":  {"bookmark_id": bm_id},
            })

    for share_id, created_at, recipe_id, via, recipe_title in shares_res.all():
        items.append({
            "type":      "share",
            "title":     f"Shared '{recipe_title}'" + (f" via {via}" if via else ""),
            "when":      created_at.isoformat(),
            "recipe_id": recipe_id,
            "metadata":  {"share_id": share_id, "via": via},
        })

    for code, badge_title, icon, awarded_at in badges_res.all():
        items.append({
            "type":      "badge_earned",
            "title":     f"Earned badge: {badge_title}",
            "when":      awarded_at.isoformat(),
            "recipe_id": None,
            "metadata":  {"code": code, "icon": icon},
        })

    if drafts_res is not None:
        for recipe_id, title, updated_at in drafts_res.all():
            items.append({
                "type":      "draft_updated",
                "title":     f"Draft updated: '{title}'",
                "when":      updated_at.isoformat(),
                "recipe_id": recipe_id,
                "metadata":  {},
            })

    items.sort(key=lambda it: it["when"], reverse=True)
    trimmed = items[:20]

    return {
        "items":       trimmed,
        "next_cursor": trimmed[-1]["when"] if len(trimmed) == 20 else None,
    }

def _verb_label(verb: str, payload: dict | None) -> str:
    """Human-readable label for Activity log verbs."""
    p = payload or {}
    return {
        "recipe.fork":      f"Forked '{p.get('parent_title', 'a recipe')}'",
        "recipe.publish":   f"Published '{p.get('title', 'a recipe')}'",
        "recipe.like":      f"Liked '{p.get('title', 'a recipe')}'",
        "comment.create":   f"Commented on '{p.get('recipe_title', 'a recipe')}'",
        "user.follow":      f"Followed {p.get('username', 'someone')}",
    }.get(verb, verb.replace(".", " ").title())


# ============================================================
# Device Revocation
# ============================================================

@profile_router.post("/me/devices/{device_id}/revoke")
async def revoke_device(
    device_id: int,
    request: Request,
    user: User = Depends(get_current_user),
):
    token = request.cookies.get("access_token")

    await revoke_device_by_id(
        device_id=device_id,
        user_id=user.id,
        access_token=token,
    )

    return {"ok": True}


@profile_router.post("/me/devices/revoke-others")
async def revoke_other_devices(
    request: Request,
    user: User = Depends(get_current_user),
):
    token = request.cookies.get("access_token")
    device_secret = request.cookies.get(DEVICE_COOKIE)
    if not device_secret:
        raise HTTPException(401, "Device missing")

    await revoke_all_other_devices(
        user_id=user.id,
        current_device_secret=device_secret,
    )

    return {"ok": True}

