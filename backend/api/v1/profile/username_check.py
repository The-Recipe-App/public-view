import re
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.username_index import username_index
from api.v1.profile.username_stream import subscribers

from api.v1.auth.utils.dependencies import get_current_user
from database.main.core.models import User

router = APIRouter(prefix="/profile", tags=["profile"])

# Username format
USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,30}$")
USERNAME_RE_FULLMATCH = USERNAME_RE.fullmatch

EMAIL_LIKE_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", re.IGNORECASE)
EMAIL_LIKE_MATCH = EMAIL_LIKE_RE.match

class UsernameCheck(BaseModel):
    username: str

@router.post("/username/check")
async def username_check(payload: UsernameCheck, user: User = Depends(get_current_user)):
    username = payload.username.strip()

    if not USERNAME_RE_FULLMATCH(username):
        result = {
            "username": username,
            "available": False,
            "reason": "invalid_format",
        }

    elif EMAIL_LIKE_MATCH(username) is not None:
        result = {
            "username": username,
            "available": False,
            "reason": "looks_like_email",
        }

    else:
        available = not username_index.exists(username)
        result = {
            "username": username,
            "available": available,
        }

    for q in subscribers.values():
        q.put_nowait(result)

    return {"ok": True}
