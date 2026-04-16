from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


# ─────────────────────────────
# Policy Fetch Schemas (STATIC FILE SYSTEM)
# ─────────────────────────────

class PolicyOut(BaseModel):
    """
    Active policy metadata returned to frontend.

    Policy content is NOT stored in DB anymore.
    Frontend fetches file_url directly.
    """

    key: str
    title: str
    description: Optional[str]

    version: str
    effective_at: datetime

    # ✅ Static file reference
    file_url: str = Field(
        ...,
        example="/static/legal/v1/tos.md",
    )

    file_format: str = Field(
        default="markdown",
        example="markdown",
    )

    # Legal audit hash (proof of exact doc)
    text_hash: str


class ActivePoliciesResponse(BaseModel):
    ok: bool = True
    policies: List[PolicyOut]


# ─────────────────────────────
# Policy Version History
# ─────────────────────────────

class PolicyVersionOut(BaseModel):
    """
    Historical policy snapshot metadata.

    Still no markdown/html blobs.
    """

    version: str
    effective_at: datetime
    is_active: bool

    file_url: str = Field(
        ...,
        example="/static/legal/v1/tos.md",
    )

    file_format: str = Field(
        default="markdown",
        example="markdown",
    )

    text_hash: str


class PolicyHistoryResponse(BaseModel):
    ok: bool = True
    versions: List[PolicyVersionOut]


# ─────────────────────────────
# Consent Payloads
# ─────────────────────────────

class AgreementRef(BaseModel):
    """
    Agreement reference sent back during consent acceptance.

    Must match:
    - policy key
    - policy version
    - hash of static file contents
    """

    key: str = Field(..., example="tos")
    version: str = Field(..., example="v1")
    text_hash: str = Field(..., example="sha256:abcd1234...")


class ConsentMeta(BaseModel):
    """
    Extra provenance context.

    Stored for compliance/audit.
    """

    flow: str = Field(..., example="registration")
    ui: str = Field(..., example="modal_v1")

    scroll_confirmed: bool = True

    locale: Optional[str] = "en"
    country: Optional[str] = None
    device: Optional[str] = None

    extra: Optional[Dict[str, Any]] = None


# ─────────────────────────────
# Pre-Registration Consent (OTP Bound)
# ─────────────────────────────

class PreRegisterConsentPayload(BaseModel):
    challenge_id: str
    agreements: List[AgreementRef]
    meta: ConsentMeta


class PreRegisterConsentResponse(BaseModel):
    ok: bool = True
    accepted: int


# ─────────────────────────────
# Authenticated User Consent
# ─────────────────────────────

class UserConsentPayload(BaseModel):
    agreements: List[AgreementRef]
    meta: ConsentMeta


class UserConsentResponse(BaseModel):
    ok: bool = True
    accepted: int


# ─────────────────────────────
# Consent Ledger Readback
# ─────────────────────────────

class UserConsentOut(BaseModel):
    agreement_key: str
    agreement_version: str
    accepted_at: datetime
    text_hash: str
    meta: Optional[Dict[str, Any]]


class MyConsentsResponse(BaseModel):
    ok: bool = True
    consents: List[UserConsentOut]
