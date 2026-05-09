"""DND (Do Not Disturb) filtering and calling-hours validation."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import pytz

from database import supabase_admin

logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")


async def filter_dnd_numbers(
    numbers: list[str],
    client_id: str,
) -> tuple[list[str], list[str]]:
    """
    Filter a list of phone numbers against DND and client blacklists.

    Args:
        numbers: Normalized phone numbers (E.164 format).
        client_id: The client's UUID for checking their specific blacklist.

    Returns:
        Tuple of (clean_numbers, blocked_numbers).
    """
    if not numbers:
        return [], []

    # Fetch global DND list matching these numbers
    dnd_response = (
        supabase_admin.table("dnd_numbers")
        .select("phone_number")
        .in_("phone_number", numbers)
        .execute()
    )
    dnd_set: set[str] = {row["phone_number"] for row in (dnd_response.data or [])}

    # Fetch client-specific blacklist
    blacklist_response = (
        supabase_admin.table("blacklist")
        .select("phone_number")
        .eq("client_id", client_id)
        .in_("phone_number", numbers)
        .execute()
    )
    blacklist_set: set[str] = {row["phone_number"] for row in (blacklist_response.data or [])}

    blocked_set = dnd_set | blacklist_set
    clean_numbers = [n for n in numbers if n not in blocked_set]
    blocked_numbers = [n for n in numbers if n in blocked_set]

    logger.info(
        "DND filter result for client %s: %d clean, %d blocked out of %d",
        client_id,
        len(clean_numbers),
        len(blocked_numbers),
        len(numbers),
    )
    return clean_numbers, blocked_numbers


async def add_to_blacklist(
    client_id: str,
    phone_number: str,
    reason: str,
) -> None:
    """
    Add a phone number to the client-specific blacklist.

    Args:
        client_id: The client's UUID.
        phone_number: Normalized phone number to block.
        reason: Human-readable reason for blocking.
    """
    record = {
        "id": str(uuid.uuid4()),
        "client_id": client_id,
        "phone_number": phone_number,
        "reason": reason,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    supabase_admin.table("blacklist").upsert(
        record, on_conflict="client_id,phone_number"
    ).execute()
    logger.info("Added %s to blacklist for client %s (reason: %s)", phone_number, client_id, reason)


async def is_within_calling_hours(schedule_start: str, schedule_end: str) -> bool:
    """
    Check whether the current IST time falls within the permitted calling window.

    Args:
        schedule_start: Start time string in "HH:MM" format (24h).
        schedule_end: End time string in "HH:MM" format (24h).

    Returns:
        True if the current IST time is within [schedule_start, schedule_end).
    """
    now_ist = datetime.now(IST)
    current_minutes = now_ist.hour * 60 + now_ist.minute

    start_h, start_m = map(int, schedule_start.split(":"))
    end_h, end_m = map(int, schedule_end.split(":"))

    start_minutes = start_h * 60 + start_m
    end_minutes = end_h * 60 + end_m

    in_window = start_minutes <= current_minutes < end_minutes
    logger.debug(
        "Calling hours check: now=%02d:%02d IST, window=%s-%s → %s",
        now_ist.hour,
        now_ist.minute,
        schedule_start,
        schedule_end,
        "allowed" if in_window else "blocked",
    )
    return in_window
