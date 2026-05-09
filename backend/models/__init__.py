import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, ForeignKey,
    Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from database import Base


def _now():
    return datetime.now(timezone.utc)


class Client(Base):
    __tablename__ = "clients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, nullable=False, unique=True)
    password_hash = Column(String, nullable=False)
    company_name = Column(String, nullable=False)
    wallet_balance = Column(BigInteger, nullable=False, default=0)  # paise
    is_active = Column(Boolean, nullable=False, default=True)
    is_admin = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="draft")  # draft/active/paused/completed/deleted
    language = Column(String, nullable=False)
    agent_name = Column(String)
    agent_gender = Column(String, default="female")
    agent_tone = Column(String, default="friendly")
    company_name = Column(String)
    product_name = Column(String)
    product_price = Column(String)
    key_benefits = Column(ARRAY(Text), default=list)
    goal = Column(String)
    transfer_condition = Column(String)
    system_prompt = Column(Text)
    calling_schedule_start = Column(String, default="09:00")
    calling_schedule_end = Column(String, default="20:00")
    calling_days = Column(ARRAY(Text), default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class PhoneNumber(Base):
    __tablename__ = "phone_numbers"
    __table_args__ = (UniqueConstraint("campaign_id", "number"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    number = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")
    callback_datetime = Column(DateTime(timezone=True))
    attempts = Column(Integer, nullable=False, default=0)
    last_attempt_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)


class Call(Base):
    __tablename__ = "calls"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    phone_number_id = Column(UUID(as_uuid=True), ForeignKey("phone_numbers.id", ondelete="CASCADE"), nullable=False)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    call_sid = Column(String, unique=True)
    status = Column(String, nullable=False, default="initiated")
    duration_seconds = Column(Integer, default=0)
    cost_paise = Column(BigInteger, default=0)
    recording_url = Column(String)
    transcript = Column(Text)
    ai_summary = Column(Text)
    lead_status = Column(String)
    follow_up_date = Column(DateTime(timezone=True))
    started_at = Column(DateTime(timezone=True))
    ended_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    amount = Column(BigInteger, nullable=False)  # positive=credit, negative=debit
    type = Column(String, nullable=False)  # topup / deduction / refund
    description = Column(Text)
    razorpay_payment_id = Column(String)
    call_id = Column(UUID(as_uuid=True), ForeignKey("calls.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)


class Blacklist(Base):
    __tablename__ = "blacklist"
    __table_args__ = (UniqueConstraint("client_id", "phone_number"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    phone_number = Column(String, nullable=False)
    reason = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)


class DndNumber(Base):
    __tablename__ = "dnd_numbers"

    phone_number = Column(String, primary_key=True)
    added_at = Column(DateTime(timezone=True), nullable=False, default=_now)
