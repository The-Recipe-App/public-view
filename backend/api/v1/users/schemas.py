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


class LoginRequest(BaseModel):
    email: EmailStr = Field(..., description="Account email")
    password: str = Field(..., min_length=8)
