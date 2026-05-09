"""Exotel call initiation, status retrieval, and retry scheduling."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import httpx

from config import settings
from database import supabase_admin
from services.queue_manager import schedule_retry

logger = logging.getLogger(__name__)

EXOTEL_BASE = "https://api.exotel.com/v1/Accounts/{sid}"
EXOTEL_TIMEOUT = 15.0  # seconds


def _exotel_auth() -> tuple[str, str]:
    return settings.exotel_api_key, settings.exotel_api_token


def _exotel_url(path: str) -> str:
    return f"{EXOTEL_BASE.format(sid=settings.exotel_sid)}/{path}"


async def initiate_call(
    phone_number: str,
    campaign_id: str,
    phone_number_id: str,
    client_id: str,
) -> str:
    """
    Dial a number via Exotel and create a call record in the DB.

    Args:
        phone_number: E.164 phone number to dial.
        campaign_id: UUID of the associated campaign.
        phone_number_id: UUID of the phone_number record.
        client_id: UUID of the owning client.

    Returns:
        The Exotel CallSid string.

    Raises:
        httpx.HTTPStatusError: On Exotel API failure.
    """
    call_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # Exotel connect.json payload
    payload = {
        "From": settings.exotel_caller_id,
        "To": phone_number,
        "CallerId": settings.exotel_caller_id,
        # Exotel will POST to our webhook when connected
        "StatusCallback": f"{settings.frontend_url.rstrip('/')}/api/webhook/exotel/call-completed",
        "Record": "true",
    }

    async with httpx.AsyncClient(timeout=EXOTEL_TIMEOUT) as client:
        response = await client.post(
            _exotel_url("Calls/connect.json"),
            data=payload,
            auth=_exotel_auth(),
        )
        response.raise_for_status()
        data = response.json()

    call_sid: str = data["Call"]["Sid"]

    # Create call record
    supabase_admin.table("calls").insert(
        {
            "id": call_id,
            "campaign_id": campaign_id,
            "phone_number_id": phone_number_id,
            "client_id": client_id,
            "call_sid": call_sid,
            "status": "initiated",
            "started_at": now,
        }
    ).execute()

    # Update phone_number record
    supabase_admin.table("phone_numbers").update(
        {
            "status": "calling",
            "last_attempt_at": now,
        }
    ).eq("id", phone_number_id).execute()

    logger.info(
        "Initiated call %s → phone_number=%s, call_sid=%s", call_id, phone_number, call_sid
    )
    return call_sid


async def get_call_status(call_sid: str) -> dict:
    """
    Fetch the current status of a call from Exotel.

    Args:
        call_sid: The Exotel CallSid.

    Returns:
        Dict with Exotel call details.
    """
    async with httpx.AsyncClient(timeout=EXOTEL_TIMEOUT) as client:
        response = await client.get(
            _exotel_url(f"Calls/{call_sid}.json"),
            auth=_exotel_auth(),
        )
        response.raise_for_status()
        return response.json().get("Call", {})


async def schedule_callback_retry(
    phone_number_id: str,
    delay_seconds: int = 3600,
) -> None:
    """
    Enqueue a retry for a phone number after a specified delay.

    Args:
        phone_number_id: UUID of the phone_number record to retry.
        delay_seconds: Delay before retrying (default 1 hour).
    """
    await schedule_retry(phone_number_id, delay_seconds)
    logger.info(
        "Scheduled callback retry for phone_number_id=%s in %ds",
        phone_number_id,
        delay_seconds,
    )
