"""DND (Do Not Disturb) filtering and calling-hours validation."""

from __future__ import annotations

import logging
from datetime import datetime

import pytz
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models import Blacklist, DndNumber

logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")


async def filter_dnd_numbers(
    db: AsyncSession,
    numbers: list[str],
    client_id,
) -> tuple[list[str], list[str]]:
    """
    Filter a list of phone numbers against DND and client blacklists.

    Args:
        db: Async database session.
        numbers: Normalized phone numbers (E.164 format).
        client_id: The client's UUID for checking their specific blacklist.

    Returns:
        Tuple of (clean_numbers, blocked_numbers).
    """
    if not numbers:
        return [], []

    # Fetch global DND list matching these numbers
    dnd_result = await db.execute(
        select(DndNumber.phone_number).where(DndNumber.phone_number.in_(numbers))
    )
    dnd_set: set[str] = {row[0] for row in dnd_result.all()}

    # Fetch client-specific blacklist
    blacklist_result = await db.execute(
        select(Blacklist.phone_number)
        .where(Blacklist.client_id == client_id)
        .where(Blacklist.phone_number.in_(numbers))
    )
    blacklist_set: set[str] = {row[0] for row in blacklist_result.all()}

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
    db: AsyncSession,
    client_id,
    phone_number: str,
    reason: str,
) -> None:
    """
    Add a phone number to the client-specific blacklist.

    Args:
        db: Async database session.
        client_id: The client's UUID.
        phone_number: Normalized phone number to block.
        reason: Human-readable reason for blocking.
    """
    stmt = pg_insert(Blacklist).values(
        client_id=client_id,
        phone_number=phone_number,
        reason=reason,
    ).on_conflict_do_nothing(index_elements=["client_id", "phone_number"])
    await db.execute(stmt)
    await db.commit()
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
