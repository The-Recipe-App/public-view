from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from pydantic import field_validator
import re


class RegisterRequest(BaseModel):
    email: EmailStr = Field(..., description="Primary account email")
    password: str = Field(..., min_length=8)
    username: Optional[str] = Field(
        None,
        min_length=3,
        max_length=150,
        description="Optional display username"
    )
    @field_validator("username")
    @classmethod
    def validate_username(cls, v):
        if v and not re.match(r"^[a-zA-Z0-9_]{3,30}$", v):
            raise ValueError("Invalid username format")
        return v

class RequestOtpRequest(BaseModel):
    email: EmailStr
    fingerprint: Optional[str] = None   # device fingerprint from client (optional but recommended)

class RequestOtpResponse(BaseModel):
    ok: bool
    challenge_id: str
    resend_cooldown: int = 30
    expires_in: int = 300  # seconds until OTP expiry

class ResendOtpRequest(BaseModel):
    email: EmailStr
    challenge_id: str

class VerifyOtpRequest(BaseModel):
    email: str = Field(..., description="Email or username")
    challenge_id: str
    code: str
    
class VerifyLoginOtpRequest(BaseModel):
    email: str
    challenge_id: str
    code: str

class RegisterWithChallengeRequest(BaseModel):
    email: EmailStr
    password: str
    username: Optional[str] = None
    challenge_id: str

class LoginRequest(BaseModel):
    identifier: str = Field(..., description="Email or username")
    password: str = Field(..., min_length=8)
