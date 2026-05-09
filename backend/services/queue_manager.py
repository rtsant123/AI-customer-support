"""Redis-based call queue management for campaigns."""

from __future__ import annotations

import logging
from typing import Optional

from main import redis_client

logger = logging.getLogger(__name__)

_QUEUE_PREFIX = "queue:campaign:"
_PAUSED_PREFIX = "paused:"
_RETRY_PREFIX = "retry:"


def _queue_key(campaign_id: str) -> str:
    return f"{_QUEUE_PREFIX}{campaign_id}"


def _paused_key(campaign_id: str) -> str:
    return f"{_PAUSED_PREFIX}{campaign_id}"


async def enqueue_campaign_calls(campaign_id: str, phone_numbers: list[str]) -> None:
    """
    Push all phone numbers onto the Redis list for this campaign.

    Args:
        campaign_id: Campaign UUID.
        phone_numbers: List of E.164 phone numbers to enqueue.
    """
    if not phone_numbers:
        return

    key = _queue_key(campaign_id)
    # RPUSH appends so processing order matches upload order
    await redis_client.rpush(key, *phone_numbers)
    logger.info("Enqueued %d numbers for campaign %s", len(phone_numbers), campaign_id)


async def get_next_call(campaign_id: str) -> Optional[str]:
    """
    Pop the next phone number from the campaign queue.

    Returns:
        Phone number string, or None if the queue is empty.
    """
    key = _queue_key(campaign_id)
    value = await redis_client.lpop(key)
    if value is None:
        return None
    # redis-py returns bytes when decode_responses=False
    return value.decode() if isinstance(value, bytes) else value


async def pause_campaign_queue(campaign_id: str) -> None:
    """Set a pause flag for the campaign so workers skip it."""
    await redis_client.set(_paused_key(campaign_id), "1")
    logger.info("Campaign %s queue paused", campaign_id)


async def resume_campaign_queue(campaign_id: str) -> None:
    """Remove the pause flag, allowing workers to process this campaign again."""
    await redis_client.delete(_paused_key(campaign_id))
    logger.info("Campaign %s queue resumed", campaign_id)


async def is_campaign_paused(campaign_id: str) -> bool:
    """Return True if the campaign has an active pause flag in Redis."""
    value = await redis_client.get(_paused_key(campaign_id))
    return value is not None


async def get_queue_size(campaign_id: str) -> int:
    """Return the number of numbers remaining in the campaign queue."""
    return await redis_client.llen(_queue_key(campaign_id))


async def schedule_retry(phone_number_id: str, delay_seconds: int) -> None:
    """
    Schedule a retry for a phone number after a delay.

    Stores the phone_number_id in a Redis sorted set with score = (now + delay).
    A background worker processes due retries by scoring up to current timestamp.

    Args:
        phone_number_id: UUID of the phone_number record.
        delay_seconds: How many seconds from now to retry.
    """
    import time

    score = time.time() + delay_seconds
    await redis_client.zadd(_RETRY_PREFIX + "scheduled", {phone_number_id: score})
    logger.info(
        "Scheduled retry for phone_number_id=%s in %ds", phone_number_id, delay_seconds
    )


async def get_due_retries(limit: int = 50) -> list[str]:
    """
    Pop all phone_number_ids whose retry time has passed.

    Args:
        limit: Maximum number of retries to fetch in one call.

    Returns:
        List of phone_number_id strings that are due for retry.
    """
    import time

    now = time.time()
    key = _RETRY_PREFIX + "scheduled"
    due: list = await redis_client.zrangebyscore(key, "-inf", now, start=0, num=limit)
    if not due:
        return []

    # Remove fetched items atomically
    await redis_client.zrem(key, *due)
    return [v.decode() if isinstance(v, bytes) else v for v in due]
