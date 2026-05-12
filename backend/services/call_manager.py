"""Twilio outbound call initiation, status retrieval, and retry scheduling."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from functools import partial

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from twilio.rest import Client as TwilioClient

from config import settings
from models import Call, PhoneNumber
from services.queue_manager import schedule_retry

logger = logging.getLogger(__name__)


def _twilio_client() -> TwilioClient:
    return TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)


async def initiate_call(
    db: AsyncSession,
    phone_number: str,
    campaign_id: str,
    phone_number_id: str,
    client_id,
) -> str:
    """
    Dial a number via Twilio and create a call record in the DB.

    Returns the Twilio CallSid string.
    """
    call_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # Twilio fetches this URL when the call connects to get TwiML instructions.
    twiml_url = (
        f"{settings.backend_url}/api/webhook/twilio/call-connected"
        f"?campaign_id={campaign_id}&phone_number_id={phone_number_id}&client_id={client_id}&call_id={call_id}"
    )
    status_callback_url = f"{settings.backend_url}/api/webhook/twilio/call-status"

    twilio = _twilio_client()
    loop = asyncio.get_event_loop()
    call = await loop.run_in_executor(
        None,
        partial(
            twilio.calls.create,
            to=phone_number,
            from_=settings.twilio_phone_number,
            url=twiml_url,
            status_callback=status_callback_url,
            status_callback_event=["completed", "failed", "no-answer", "busy"],
            status_callback_method="POST",
            record=True,
            recording_status_callback=f"{settings.backend_url}/api/webhook/twilio/recording",
            recording_status_callback_method="POST",
        ),
    )

    call_sid: str = call.sid

    call_record = Call(
        id=call_id,
        campaign_id=uuid.UUID(campaign_id),
        phone_number_id=uuid.UUID(phone_number_id),
        client_id=client_id,
        call_sid=call_sid,
        status="initiated",
        started_at=now,
    )
    db.add(call_record)

    await db.execute(
        update(PhoneNumber)
        .where(PhoneNumber.id == uuid.UUID(phone_number_id))
        .values(status="calling", last_attempt_at=now)
    )
    await db.commit()

    logger.info("Initiated call %s → %s (Twilio SID: %s)", call_id, phone_number, call_sid)
    return call_sid


async def get_call_status(call_sid: str) -> dict:
    """Fetch the current status of a call from Twilio."""
    client = _twilio_client()
    call = client.calls(call_sid).fetch()
    return {
        "sid": call.sid,
        "status": call.status,
        "duration": call.duration,
        "direction": call.direction,
    }


async def schedule_callback_retry(
    phone_number_id: str,
    delay_seconds: int = 3600,
) -> None:
    """Enqueue a retry for a phone number after a specified delay."""
    await schedule_retry(phone_number_id, delay_seconds)
    logger.info(
        "Scheduled callback retry for phone_number_id=%s in %ds",
        phone_number_id,
        delay_seconds,
    )
