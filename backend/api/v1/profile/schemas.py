# api/v1/profile/schemas.py

from pydantic import BaseModel, HttpUrl, Field, EmailStr, field_validator
from typing import Optional, List
from datetime import datetime


class ProfileUpdateSchema(BaseModel):
    username: Optional[str] = Field(None, min_length=3, max_length=30)
    bio: Optional[str] = Field(None, max_length=500)
    location: Optional[str] = Field(None, max_length=100)
    website: Optional[str] = Field(None, max_length=2000)
    twitter: Optional[str] = Field(None, min_length=1, max_length=15, pattern=r"^[A-Za-z0-9_]{1,15}$")
    youtube: Optional[str] = Field(None, min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_]{1,50}$")

    @field_validator("username", "bio", "location", "website", "twitter", "youtube", mode="before")
    @classmethod
    def empty_string_to_none(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v


class BadgeOut(BaseModel):
    code: str
    title: str
    icon: str
    awarded_at: datetime


class ReputationOut(BaseModel):
    score: int
    level: str
    next_level: Optional[str]
    current_threshold: int
    next_threshold: Optional[int]
    progress_pct: float
    can_vote: bool
    can_moderate: bool
    can_lock: bool


class SecurityOut(BaseModel):
    email: str | None = None
    is_banned: bool
    plan: str
    can_vote: bool
    can_moderate: bool
    identities: list[dict]
    devices: list[dict]

class DeviceOut(BaseModel):
    id: int
    user_agent: str
    first_seen_at: datetime
    last_seen_at: datetime
    is_trusted: bool
    is_current: bool


class PasskeyOut(BaseModel):
    id: str
    name: str
    created_at: datetime
    last_used_at: Optional[datetime]


class SecurityOut(BaseModel):
    email: str
    is_banned: bool
    plan: str
    can_vote: bool
    can_moderate: bool
    identities: list
    devices: List[DeviceOut]
    passkeys: List[PasskeyOut]

class EmailUpdateSchema(BaseModel):
    email: EmailStr

class PasswordChangeSchema(BaseModel):
    current_password: str
    new_password: str
