"""Campaign management routes."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import phonenumbers
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from database import supabase_admin
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


def _assert_campaign_belongs_to_client(campaign: Optional[dict], campaign_id: str, client_id: str) -> dict:
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    if campaign["client_id"] != client_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return campaign


# ---------------------------------------------------------------------------
# List / Create
# ---------------------------------------------------------------------------

@router.get("")
async def list_campaigns(current_user: dict = Depends(get_current_user)) -> JSONResponse:
    """Return all campaigns belonging to the current client."""
    response = (
        supabase_admin.table("campaigns")
        .select("*")
        .eq("client_id", current_user["id"])
        .eq("is_deleted", False)
        .order("created_at", desc=True)
        .execute()
    )
    return JSONResponse(content={"campaigns": response.data or []})


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_campaign(
    body: CampaignCreate,
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Create a new campaign and auto-generate its system prompt."""
    campaign_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    campaign_data = body.model_dump()
    system_prompt = build_system_prompt(campaign_data)

    record = {
        "id": campaign_id,
        "client_id": current_user["id"],
        "status": "draft",
        "system_prompt": system_prompt,
        "is_deleted": False,
        "created_at": now,
        **campaign_data,
    }

    supabase_admin.table("campaigns").insert(record).execute()
    logger.info("Created campaign %s for client %s", campaign_id, current_user["id"])

    return JSONResponse(status_code=status.HTTP_201_CREATED, content={"campaign": record})


# ---------------------------------------------------------------------------
# Single campaign operations
# ---------------------------------------------------------------------------

@router.get("/{campaign_id}")
async def get_campaign(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    response = (
        supabase_admin.table("campaigns")
        .select("*")
        .eq("id", campaign_id)
        .eq("is_deleted", False)
        .single()
        .execute()
    )
    campaign = _assert_campaign_belongs_to_client(response.data, campaign_id, current_user["id"])
    return JSONResponse(content={"campaign": campaign})


@router.put("/{campaign_id}")
async def update_campaign(
    campaign_id: str,
    body: CampaignUpdate,
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Update a campaign. Only allowed when status is draft or paused."""
    existing_resp = (
        supabase_admin.table("campaigns")
        .select("*")
        .eq("id", campaign_id)
        .eq("is_deleted", False)
        .single()
        .execute()
    )
    campaign = _assert_campaign_belongs_to_client(existing_resp.data, campaign_id, current_user["id"])

    if campaign["status"] not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot edit campaign with status '{campaign['status']}'. Pause it first.",
        )

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        return JSONResponse(content={"campaign": campaign})

    # If any prompt-affecting field changed, rebuild the system prompt
    prompt_fields = {
        "language", "agent_name", "agent_gender", "agent_tone", "company_name",
        "product_name", "product_price", "key_benefits", "goal", "transfer_condition",
    }
    if prompt_fields & set(updates.keys()):
        merged = {**campaign, **updates}
        updates["system_prompt"] = build_system_prompt(merged)

    supabase_admin.table("campaigns").update(updates).eq("id", campaign_id).execute()

    refreshed = (
        supabase_admin.table("campaigns").select("*").eq("id", campaign_id).single().execute()
    )
    return JSONResponse(content={"campaign": refreshed.data})


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
) -> None:
    """Soft-delete a campaign."""
    existing_resp = (
        supabase_admin.table("campaigns")
        .select("id, client_id")
        .eq("id", campaign_id)
        .eq("is_deleted", False)
        .single()
        .execute()
    )
    _assert_campaign_belongs_to_client(existing_resp.data, campaign_id, current_user["id"])

    supabase_admin.table("campaigns").update({"is_deleted": True}).eq("id", campaign_id).execute()
    logger.info("Soft-deleted campaign %s", campaign_id)


# ---------------------------------------------------------------------------
# Campaign lifecycle
# ---------------------------------------------------------------------------

@router.post("/{campaign_id}/launch")
async def launch_campaign(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Launch a draft/paused campaign: set active and enqueue pending numbers."""
    existing_resp = (
        supabase_admin.table("campaigns")
        .select("*")
        .eq("id", campaign_id)
        .eq("is_deleted", False)
        .single()
        .execute()
    )
    campaign = _assert_campaign_belongs_to_client(existing_resp.data, campaign_id, current_user["id"])

    if campaign["status"] == "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Campaign is already active",
        )

    # Fetch all pending numbers
    numbers_resp = (
        supabase_admin.table("phone_numbers")
        .select("id, number")
        .eq("campaign_id", campaign_id)
        .eq("status", "pending")
        .execute()
    )
    pending = numbers_resp.data or []

    if not pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending numbers to call. Upload phone numbers first.",
        )

    phone_number_ids = [row["id"] for row in pending]
    await enqueue_campaign_calls(campaign_id, phone_number_ids)

    supabase_admin.table("campaigns").update({"status": "active"}).eq("id", campaign_id).execute()
    logger.info("Launched campaign %s with %d numbers", campaign_id, len(pending))

    return JSONResponse(content={"status": "active", "enqueued": len(pending)})


@router.post("/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Pause an active campaign."""
    existing_resp = (
        supabase_admin.table("campaigns")
        .select("id, client_id, status")
        .eq("id", campaign_id)
        .eq("is_deleted", False)
        .single()
        .execute()
    )
    campaign = _assert_campaign_belongs_to_client(existing_resp.data, campaign_id, current_user["id"])

    if campaign["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Campaign is not active",
        )

    await pause_campaign_queue(campaign_id)
    supabase_admin.table("campaigns").update({"status": "paused"}).eq("id", campaign_id).execute()
    logger.info("Paused campaign %s", campaign_id)

    return JSONResponse(content={"status": "paused"})


@router.post("/{campaign_id}/resume")
async def resume_campaign(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Resume a paused campaign."""
    existing_resp = (
        supabase_admin.table("campaigns")
        .select("id, client_id, status")
        .eq("id", campaign_id)
        .eq("is_deleted", False)
        .single()
        .execute()
    )
    campaign = _assert_campaign_belongs_to_client(existing_resp.data, campaign_id, current_user["id"])

    if campaign["status"] != "paused":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Campaign is not paused",
        )

    await resume_campaign_queue(campaign_id)
    supabase_admin.table("campaigns").update({"status": "active"}).eq("id", campaign_id).execute()
    logger.info("Resumed campaign %s", campaign_id)

    return JSONResponse(content={"status": "active"})


# ---------------------------------------------------------------------------
# Phone numbers
# ---------------------------------------------------------------------------

@router.post("/{campaign_id}/numbers", status_code=status.HTTP_201_CREATED)
async def upload_numbers(
    campaign_id: str,
    body: PhoneNumberUpload,
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """
    Upload phone numbers to a campaign.

    Validates format, deduplicates, filters DND/blacklist, and inserts.
    """
    existing_resp = (
        supabase_admin.table("campaigns")
        .select("id, client_id")
        .eq("id", campaign_id)
        .eq("is_deleted", False)
        .single()
        .execute()
    )
    _assert_campaign_belongs_to_client(existing_resp.data, campaign_id, current_user["id"])

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
    existing_numbers_resp = (
        supabase_admin.table("phone_numbers")
        .select("number")
        .eq("campaign_id", campaign_id)
        .execute()
    )
    existing_set = {row["number"] for row in (existing_numbers_resp.data or [])}
    new_numbers = [n for n in unique if n not in existing_set]

    # DND filter
    clean_numbers, blocked_numbers = await filter_dnd_numbers(new_numbers, current_user["id"])

    # Batch insert clean numbers
    now = datetime.now(timezone.utc).isoformat()
    records = [
        {
            "id": str(uuid.uuid4()),
            "campaign_id": campaign_id,
            "client_id": current_user["id"],
            "number": num,
            "status": "pending",
            "attempts": 0,
            "created_at": now,
        }
        for num in clean_numbers
    ]

    if records:
        supabase_admin.table("phone_numbers").insert(records).execute()

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
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """List phone numbers for a campaign with pagination."""
    existing_resp = (
        supabase_admin.table("campaigns")
        .select("id, client_id")
        .eq("id", campaign_id)
        .eq("is_deleted", False)
        .single()
        .execute()
    )
    _assert_campaign_belongs_to_client(existing_resp.data, campaign_id, current_user["id"])

    offset = (page - 1) * page_size
    numbers_resp = (
        supabase_admin.table("phone_numbers")
        .select("*")
        .eq("campaign_id", campaign_id)
        .order("created_at", desc=False)
        .range(offset, offset + page_size - 1)
        .execute()
    )

    return JSONResponse(
        content={
            "numbers": numbers_resp.data or [],
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/{campaign_id}/stats")
async def campaign_stats(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Return aggregate call outcome statistics for a campaign."""
    existing_resp = (
        supabase_admin.table("campaigns")
        .select("id, client_id")
        .eq("id", campaign_id)
        .eq("is_deleted", False)
        .single()
        .execute()
    )
    _assert_campaign_belongs_to_client(existing_resp.data, campaign_id, current_user["id"])

    numbers_resp = (
        supabase_admin.table("phone_numbers")
        .select("status, lead_status")
        .eq("campaign_id", campaign_id)
        .execute()
    )
    rows = numbers_resp.data or []

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
        s = row.get("status", "pending")
        ls = (row.get("lead_status") or "").lower().replace(" ", "_")

        if s == "pending":
            stats["pending"] += 1
        elif s == "called":
            stats["called"] += 1
            if ls == "interested":
                stats["interested"] += 1
            elif ls == "not_interested":
                stats["not_interested"] += 1
            elif ls == "callback":
                stats["callback"] += 1
            elif ls == "wrong_number":
                stats["wrong_number"] += 1
            elif ls == "language_barrier":
                stats["language_barrier"] += 1
        elif s == "dnd_blocked":
            stats["dnd_blocked"] += 1

    return JSONResponse(content={"stats": stats})
