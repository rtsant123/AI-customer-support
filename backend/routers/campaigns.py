"""Campaign management routes."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import phonenumbers
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import select, update, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Campaign, PhoneNumber, Client
from models.schemas import (
    CampaignCreate,
    CampaignStats,
    CampaignUpdate,
    PhoneNumberUpload,
)
from routers.auth import get_current_user
from services.dnd_filter import filter_dnd_numbers
from services.prompt_builder import build_system_prompt
from services.queue_manager import (
    enqueue_campaign_calls,
    is_campaign_paused,
    pause_campaign_queue,
    resume_campaign_queue,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/campaigns", tags=["campaigns"])

EDITABLE_STATUSES = {"draft", "paused"}


def _normalize_phone(raw: str) -> Optional[str]:
    """
    Parse and normalize a phone number to E.164 format (+91XXXXXXXXXX for India).

    Returns None if the number is invalid.
    """
    try:
        parsed = phonenumbers.parse(raw, "IN")
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass
    return None


def _assert_campaign_belongs_to_client(campaign: Optional[Campaign], campaign_id: str, client_id) -> Campaign:
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    if str(campaign.client_id) != str(client_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return campaign


def _campaign_dict(c: Campaign) -> dict:
    return {
        "id": str(c.id),
        "client_id": str(c.client_id),
        "name": c.name,
        "status": c.status,
        "language": c.language,
        "agent_name": c.agent_name,
        "agent_gender": c.agent_gender,
        "agent_tone": c.agent_tone,
        "company_name": c.company_name,
        "product_name": c.product_name,
        "product_price": c.product_price,
        "key_benefits": c.key_benefits or [],
        "goal": c.goal,
        "transfer_condition": c.transfer_condition,
        "system_prompt": c.system_prompt,
        "calling_schedule_start": c.calling_schedule_start,
        "calling_schedule_end": c.calling_schedule_end,
        "calling_days": c.calling_days or [],
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _phone_number_dict(p: PhoneNumber) -> dict:
    return {
        "id": str(p.id),
        "campaign_id": str(p.campaign_id),
        "client_id": str(p.client_id),
        "number": p.number,
        "status": p.status,
        "attempts": p.attempts,
        "last_attempt_at": p.last_attempt_at.isoformat() if p.last_attempt_at else None,
        "callback_datetime": p.callback_datetime.isoformat() if p.callback_datetime else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


# ---------------------------------------------------------------------------
# List / Create
# ---------------------------------------------------------------------------

@router.get("")
async def list_campaigns(
    current_user: Client = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Return all campaigns belonging to the current client."""
    result = await db.execute(
        select(Campaign)
        .where(Campaign.client_id == current_user.id)
        .where(Campaign.status != "deleted")
        .order_by(Campaign.created_at.desc())
    )
    campaigns = result.scalars().all()
    return JSONResponse(content={"campaigns": [_campaign_dict(c) for c in campaigns]})


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_campaign(
    body: CampaignCreate,
    current_user: Client = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Create a new campaign and auto-generate its system prompt."""
    campaign_data = body.model_dump()
    system_prompt = build_system_prompt(campaign_data)

    campaign = Campaign(
        client_id=current_user.id,
        status="draft",
        system_prompt=system_prompt,
        **campaign_data,
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    logger.info("Created campaign %s for client %s", campaign.id, current_user.id)

    return JSONResponse(status_code=status.HTTP_201_CREATED, content={"campaign": _campaign_dict(campaign)})


# ---------------------------------------------------------------------------
# Single campaign operations
# ---------------------------------------------------------------------------

@router.get("/{campaign_id}")
async def get_campaign(
    campaign_id: str,
    current_user: Client = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    result = await db.execute(
        select(Campaign)
        .where(Campaign.id == uuid.UUID(campaign_id))
        .where(Campaign.status != "deleted")
    )
    campaign = _assert_campaign_belongs_to_client(result.scalar_one_or_none(), campaign_id, current_user.id)
    return JSONResponse(content={"campaign": _campaign_dict(campaign)})


@router.put("/{campaign_id}")
async def update_campaign(
    campaign_id: str,
    body: CampaignUpdate,
    current_user: Client = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Update a campaign. Only allowed when status is draft or paused."""
    result = await db.execute(
        select(Campaign)
        .where(Campaign.id == uuid.UUID(campaign_id))
        .where(Campaign.status != "deleted")
    )
    campaign = _assert_campaign_belongs_to_client(result.scalar_one_or_none(), campaign_id, current_user.id)

    if campaign.status not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot edit campaign with status '{campaign.status}'. Pause it first.",
        )

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        return JSONResponse(content={"campaign": _campaign_dict(campaign)})

    # If any prompt-affecting field changed, rebuild the system prompt
    prompt_fields = {
        "language", "agent_name", "agent_gender", "agent_tone", "company_name",
        "product_name", "product_price", "key_benefits", "goal", "transfer_condition",
    }
    if prompt_fields & set(updates.keys()):
        # Build merged dict from current campaign + updates
        current_data = _campaign_dict(campaign)
        merged = {**current_data, **updates}
        updates["system_prompt"] = build_system_prompt(merged)

    await db.execute(
        update(Campaign)
        .where(Campaign.id == uuid.UUID(campaign_id))
        .values(**updates)
    )
    await db.commit()

    # Refresh and return
    refreshed_result = await db.execute(select(Campaign).where(Campaign.id == uuid.UUID(campaign_id)))
    refreshed = refreshed_result.scalar_one()
    return JSONResponse(content={"campaign": _campaign_dict(refreshed)})


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign_id: str,
    current_user: Client = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete a campaign by setting status to 'deleted'."""
    result = await db.execute(
        select(Campaign)
        .where(Campaign.id == uuid.UUID(campaign_id))
        .where(Campaign.status != "deleted")
    )
    _assert_campaign_belongs_to_client(result.scalar_one_or_none(), campaign_id, current_user.id)

    await db.execute(
        update(Campaign)
        .where(Campaign.id == uuid.UUID(campaign_id))
        .values(status="deleted")
    )
    await db.commit()
    logger.info("Soft-deleted campaign %s", campaign_id)


# ---------------------------------------------------------------------------
# Campaign lifecycle
# ---------------------------------------------------------------------------

@router.post("/{campaign_id}/launch")
async def launch_campaign(
    campaign_id: str,
    current_user: Client = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Launch a draft/paused campaign: set active and enqueue pending numbers."""
    result = await db.execute(
        select(Campaign)
        .where(Campaign.id == uuid.UUID(campaign_id))
        .where(Campaign.status != "deleted")
    )
    campaign = _assert_campaign_belongs_to_client(result.scalar_one_or_none(), campaign_id, current_user.id)

    if campaign.status == "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Campaign is already active",
        )

    # Fetch all pending numbers
    numbers_result = await db.execute(
        select(PhoneNumber)
        .where(PhoneNumber.campaign_id == uuid.UUID(campaign_id))
        .where(PhoneNumber.status == "pending")
    )
    pending = numbers_result.scalars().all()

    if not pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending numbers to call. Upload phone numbers first.",
        )

    phone_number_ids = [str(row.id) for row in pending]
    await enqueue_campaign_calls(campaign_id, phone_number_ids)

    await db.execute(
        update(Campaign)
        .where(Campaign.id == uuid.UUID(campaign_id))
        .values(status="active")
    )
    await db.commit()
    logger.info("Launched campaign %s with %d numbers", campaign_id, len(pending))

    return JSONResponse(content={"status": "active", "enqueued": len(pending)})


@router.post("/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: str,
    current_user: Client = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Pause an active campaign."""
    result = await db.execute(
        select(Campaign)
        .where(Campaign.id == uuid.UUID(campaign_id))
        .where(Campaign.status != "deleted")
    )
    campaign = _assert_campaign_belongs_to_client(result.scalar_one_or_none(), campaign_id, current_user.id)

    if campaign.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Campaign is not active",
        )

    await pause_campaign_queue(campaign_id)
    await db.execute(
        update(Campaign)
        .where(Campaign.id == uuid.UUID(campaign_id))
        .values(status="paused")
    )
    await db.commit()
    logger.info("Paused campaign %s", campaign_id)

    return JSONResponse(content={"status": "paused"})


@router.post("/{campaign_id}/resume")
async def resume_campaign(
    campaign_id: str,
    current_user: Client = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Resume a paused campaign."""
    result = await db.execute(
        select(Campaign)
        .where(Campaign.id == uuid.UUID(campaign_id))
        .where(Campaign.status != "deleted")
    )
    campaign = _assert_campaign_belongs_to_client(result.scalar_one_or_none(), campaign_id, current_user.id)

    if campaign.status != "paused":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Campaign is not paused",
        )

    await resume_campaign_queue(campaign_id)
    await db.execute(
        update(Campaign)
        .where(Campaign.id == uuid.UUID(campaign_id))
        .values(status="active")
    )
    await db.commit()
    logger.info("Resumed campaign %s", campaign_id)

    return JSONResponse(content={"status": "active"})


# ---------------------------------------------------------------------------
# Phone numbers
# ---------------------------------------------------------------------------

@router.post("/{campaign_id}/numbers", status_code=status.HTTP_201_CREATED)
async def upload_numbers(
    campaign_id: str,
    body: PhoneNumberUpload,
    current_user: Client = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """
    Upload phone numbers to a campaign.

    Validates format, deduplicates, filters DND/blacklist, and inserts.
    """
    result = await db.execute(
        select(Campaign)
        .where(Campaign.id == uuid.UUID(campaign_id))
        .where(Campaign.status != "deleted")
    )
    _assert_campaign_belongs_to_client(result.scalar_one_or_none(), campaign_id, current_user.id)

    # Normalize and validate
    normalized: list[str] = []
    invalid: list[str] = []
    for raw in body.numbers:
        e164 = _normalize_phone(raw.strip())
        if e164:
            normalized.append(e164)
        else:
            invalid.append(raw)

    # Deduplicate preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for n in normalized:
        if n not in seen:
            seen.add(n)
            unique.append(n)

    # Filter existing numbers already in this campaign
    existing_result = await db.execute(
        select(PhoneNumber.number)
        .where(PhoneNumber.campaign_id == uuid.UUID(campaign_id))
    )
    existing_set = {row[0] for row in existing_result.all()}
    new_numbers = [n for n in unique if n not in existing_set]

    # DND filter
    clean_numbers, blocked_numbers = await filter_dnd_numbers(db, new_numbers, current_user.id)

    # Batch insert clean numbers
    records = [
        PhoneNumber(
            campaign_id=uuid.UUID(campaign_id),
            client_id=current_user.id,
            number=num,
            status="pending",
            attempts=0,
        )
        for num in clean_numbers
    ]

    if records:
        db.add_all(records)
        await db.commit()

    logger.info(
        "Uploaded %d numbers to campaign %s: %d clean, %d blocked, %d invalid, %d duplicate",
        len(body.numbers),
        campaign_id,
        len(clean_numbers),
        len(blocked_numbers),
        len(invalid),
        len(unique) - len(new_numbers),
    )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "added": len(clean_numbers),
            "blocked_dnd": len(blocked_numbers),
            "invalid": len(invalid),
            "duplicate": len(unique) - len(new_numbers),
        },
    )


@router.get("/{campaign_id}/numbers")
async def list_numbers(
    campaign_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: Client = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """List phone numbers for a campaign with pagination."""
    result = await db.execute(
        select(Campaign)
        .where(Campaign.id == uuid.UUID(campaign_id))
        .where(Campaign.status != "deleted")
    )
    _assert_campaign_belongs_to_client(result.scalar_one_or_none(), campaign_id, current_user.id)

    offset = (page - 1) * page_size
    numbers_result = await db.execute(
        select(PhoneNumber)
        .where(PhoneNumber.campaign_id == uuid.UUID(campaign_id))
        .order_by(PhoneNumber.created_at.asc())
        .offset(offset)
        .limit(page_size)
    )
    numbers = numbers_result.scalars().all()

    return JSONResponse(
        content={
            "numbers": [_phone_number_dict(p) for p in numbers],
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/{campaign_id}/stats")
async def campaign_stats(
    campaign_id: str,
    current_user: Client = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Return aggregate call outcome statistics for a campaign."""
    result = await db.execute(
        select(Campaign)
        .where(Campaign.id == uuid.UUID(campaign_id))
        .where(Campaign.status != "deleted")
    )
    _assert_campaign_belongs_to_client(result.scalar_one_or_none(), campaign_id, current_user.id)

    numbers_result = await db.execute(
        select(PhoneNumber.status, PhoneNumber.callback_datetime)
        .where(PhoneNumber.campaign_id == uuid.UUID(campaign_id))
    )
    rows = numbers_result.all()

    stats: dict[str, int] = {
        "total": len(rows),
        "pending": 0,
        "called": 0,
        "interested": 0,
        "not_interested": 0,
        "callback": 0,
        "wrong_number": 0,
        "language_barrier": 0,
        "dnd_blocked": 0,
    }

    for row in rows:
        s = (row[0] or "pending").lower()

        if s == "pending":
            stats["pending"] += 1
        elif s == "called":
            stats["called"] += 1
        elif s == "interested":
            stats["called"] += 1
            stats["interested"] += 1
        elif s == "not_interested":
            stats["called"] += 1
            stats["not_interested"] += 1
        elif s == "callback":
            stats["called"] += 1
            stats["callback"] += 1
        elif s == "wrong_number":
            stats["called"] += 1
            stats["wrong_number"] += 1
        elif s == "language_barrier":
            stats["called"] += 1
            stats["language_barrier"] += 1
        elif s == "dnd_blocked":
            stats["dnd_blocked"] += 1

    return JSONResponse(content={"stats": stats})
