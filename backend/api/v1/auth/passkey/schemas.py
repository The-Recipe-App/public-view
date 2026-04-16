# api/v1/auth/passkey/schemas.py

from pydantic import BaseModel
from typing import Any, Dict, Optional, List

class PasskeyRegisterOptionsRequest(BaseModel):
    pass

class PasskeyRegisterOptionsResponse(BaseModel):
    options: Dict[str, Any]

class PasskeyRegisterVerifyRequest(BaseModel):
    attestation: Dict[str, Any]
    label: str

class PasskeyLoginOptionsRequest(BaseModel):
    identifier: str  # email or username

class PasskeyLoginOptionsResponse(BaseModel):
    options: Dict[str, Any]

class PasskeyLoginVerifyRequest(BaseModel):
    assertion: Dict[str, Any]
