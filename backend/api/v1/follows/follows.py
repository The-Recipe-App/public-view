from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from database.main.core.session import get_async_session
from database.main.core.models import UserFollow, User, Activity
from api.v1.auth.utils.dependencies import get_current_user, get_current_user_optional

router = APIRouter(prefix="/follows", tags=["follows"])


@router.post("/{username}")
async def toggle_follow(
    username: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    target = await session.scalar(select(User).where(User.username == username))
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == user.id:
        raise HTTPException(status_code=400, detail="Cannot follow yourself")

    existing = await session.scalar(
        select(UserFollow).where(
            UserFollow.follower_id == user.id,
            UserFollow.following_id == target.id,
        )
    )

    if existing:
        await session.delete(existing)
        following = False
    else:
        session.add(UserFollow(follower_id=user.id, following_id=target.id))
        session.add(
            Activity(
                user_id=user.id,
                verb="user.follow",
                subject_table="users",
                subject_id=target.id,
            )
        )
        following = True

    await session.commit()
    return {"ok": True, "following": following}


@router.get("/{username}/status")
async def follow_status(
    username: str,
    viewer: User = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_async_session),
):
    target = await session.scalar(select(User).where(User.username == username))
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    followers_count = await session.scalar(
        select(func.count())
        .select_from(UserFollow)
        .where(UserFollow.following_id == target.id)
    )
    following_count = await session.scalar(
        select(func.count())
        .select_from(UserFollow)
        .where(UserFollow.follower_id == target.id)
    )

    is_following = False
    if viewer and viewer.id != target.id:
        is_following = (
            await session.scalar(
                select(UserFollow).where(
                    UserFollow.follower_id == viewer.id,
                    UserFollow.following_id == target.id,
                )
            )
            is not None
        )

    return {
        "followers_count": followers_count or 0,
        "following_count": following_count or 0,
        "is_following": is_following,
    }
