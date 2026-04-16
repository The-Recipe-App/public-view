from fastapi import Request
from sqladmin.authentication import AuthenticationBackend

from api.v1.auth.utils.security import decode_access_token
from database.main.core.session import get_async_session
from database.main.core.models import User
#from core.config import settings  # or wherever your settings live

ADMIN_SESSION_SECRET = "secret"

class AdminAuth(AuthenticationBackend):
    """
    Controls access to /admin
    """

    def __init__(self):
        super().__init__(secret_key=ADMIN_SESSION_SECRET)

    async def authenticate(self, request: Request) -> bool:
        token = request.cookies.get("access_token")
        if not token:
            return False

        try:
            payload = decode_access_token(token)
        except Exception:
            return False

        user_id = payload.get("sub")
        if not user_id:
            return False

        async with get_async_session() as session:
            user = await session.get(User, user_id)
            return bool(user and user.is_admin)

    # 🚫 IMPORTANT: disable login/logout entirely
    async def login(self, request: Request) -> bool:
        return False

    async def logout(self, request: Request) -> bool:
        return True
