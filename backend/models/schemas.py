from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    company_name: str = Field(min_length=1, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    user_id: str
    email: str
    company_name: str


# ---------------------------------------------------------------------------
# Campaign
# ---------------------------------------------------------------------------

class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    language: Literal["hindi", "english", "bangla", "tamil"]
    agent_name: str = Field(min_length=1, max_length=50)
    agent_gender: Literal["male", "female"]
    agent_tone: Literal["friendly", "professional", "urgent"]
    company_name: str = Field(min_length=1, max_length=100)
    product_name: str = Field(min_length=1, max_length=100)
    product_price: str = Field(min_length=1, max_length=50)
    key_benefits: list[str] = Field(min_length=1, max_length=3)
    goal: Literal["qualify", "book_appointment", "reminder", "survey"]
    transfer_condition: str = Field(min_length=1, max_length=500)
    calling_schedule_start: str = Field(pattern=r"^\d{2}:\d{2}$")
    calling_schedule_end: str = Field(pattern=r"^\d{2}:\d{2}$")
    calling_days: list[str] = Field(
        min_length=1,
        max_length=7,
        description="List of days: monday, tuesday, ...",
    )


class CampaignUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    language: Optional[Literal["hindi", "english", "bangla", "tamil"]] = None
    agent_name: Optional[str] = Field(None, min_length=1, max_length=50)
    agent_gender: Optional[Literal["male", "female"]] = None
    agent_tone: Optional[Literal["friendly", "professional", "urgent"]] = None
    company_name: Optional[str] = Field(None, min_length=1, max_length=100)
    product_name: Optional[str] = Field(None, min_length=1, max_length=100)
    product_price: Optional[str] = Field(None, min_length=1, max_length=50)
    key_benefits: Optional[list[str]] = Field(None, max_length=3)
    goal: Optional[Literal["qualify", "book_appointment", "reminder", "survey"]] = None
    transfer_condition: Optional[str] = Field(None, min_length=1, max_length=500)
    calling_schedule_start: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    calling_schedule_end: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    calling_days: Optional[list[str]] = Field(None, max_length=7)


class CampaignResponse(BaseModel):
    id: str
    client_id: str
    name: str
    language: str
    agent_name: str
    agent_gender: str
    agent_tone: str
    company_name: str
    product_name: str
    product_price: str
    key_benefits: list[str]
    goal: str
    transfer_condition: str
    calling_schedule_start: str
    calling_schedule_end: str
    calling_days: list[str]
    status: str
    system_prompt: Optional[str] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Phone Numbers
# ---------------------------------------------------------------------------

class PhoneNumberUpload(BaseModel):
    numbers: list[str] = Field(min_length=1)


class PhoneNumberResponse(BaseModel):
    id: str
    campaign_id: str
    number: str
    status: str
    attempts: int
    last_attempt_at: Optional[datetime] = None
    callback_datetime: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Calls
# ---------------------------------------------------------------------------

class CallResponse(BaseModel):
    id: str
    campaign_id: str
    phone_number_id: str
    status: str
    duration_seconds: Optional[int] = None
    cost_paise: Optional[int] = None
    recording_url: Optional[str] = None
    transcript: Optional[str] = None
    ai_summary: Optional[str] = None
    lead_status: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Wallet
# ---------------------------------------------------------------------------

class WalletBalance(BaseModel):
    balance_paise: int
    balance_inr: float


class TopupRequest(BaseModel):
    amount_paise: int = Field(ge=10000, description="Minimum top-up: ₹100 (10000 paise)")


class TopupResponse(BaseModel):
    order_id: str
    amount: int
    currency: str
    key_id: str


class TransactionResponse(BaseModel):
    id: str
    amount_paise: int
    type: str
    description: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Exotel Webhooks
# ---------------------------------------------------------------------------

class ExotelCallConnected(BaseModel):
    CallSid: str
    From: str
    To: str
    Direction: Optional[str] = None
    Status: Optional[str] = None


class ExotelCallCompleted(BaseModel):
    CallSid: str
    Status: str
    Duration: Optional[str] = "0"
    RecordingUrl: Optional[str] = None


# ---------------------------------------------------------------------------
# Campaign Stats
# ---------------------------------------------------------------------------

class CampaignStats(BaseModel):
    total: int
    pending: int
    called: int
    interested: int
    not_interested: int
    callback: int
    wrong_number: int
    language_barrier: int
    dnd_blocked: int
