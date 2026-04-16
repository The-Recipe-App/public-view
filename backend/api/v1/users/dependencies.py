from fastapi import Depends, Header, Request, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import secrets

from database.main.core.session import get_async_session
from database.main.core.models import User
from api.v1.auth.utils.security import decode_access_token
from api.v1.auth.errors import auth_failed


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
) -> User:
    token = request.cookies.get("access_token")

    # 1️⃣ Ensure cookie is present
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    # 2️⃣ Decode & validate token
    try:
        user_id = decode_access_token(token)
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )

    # 3️⃣ Load user
    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user or user.is_banned:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )

    return user


def generate_username() -> str:
    return f"user_{secrets.token_hex(4)}"

async def allocate_unique_username(session: AsyncSession = Depends(get_async_session),) -> str:
    while True:
        candidate = generate_username()
        exists = await session.scalar(
            select(User.id).where(User.username == candidate)
        )
        if not exists:
            return candidate
