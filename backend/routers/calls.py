"""Call history and recording routes."""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from typing import Optional

import boto3
from botocore.config import Config
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from models import Call, Client
from routers.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calls", tags=["calls"])

_R2_SIGNED_URL_EXPIRY = 3600  # seconds


def _get_r2_client():
    """Build an S3-compatible boto3 client for Cloudflare R2."""
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def _call_dict(c: Call) -> dict:
    return {
        "id": str(c.id),
        "campaign_id": str(c.campaign_id),
        "phone_number_id": str(c.phone_number_id),
        "client_id": str(c.client_id),
        "call_sid": c.call_sid,
        "status": c.status,
        "duration_seconds": c.duration_seconds,
        "cost_paise": c.cost_paise,
        "recording_url": c.recording_url,
        "transcript": c.transcript,
        "ai_summary": c.ai_summary,
        "lead_status": c.lead_status,
        "started_at": c.started_at.isoformat() if c.started_at else None,
        "ended_at": c.ended_at.isoformat() if c.ended_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.get("")
async def list_calls(
    campaign_id: Optional[str] = Query(None),
    lead_status: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: Client = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """
    List calls for the current client with optional filters.

    Filters: campaign_id, lead_status, date_from (started_at >=), date_to (started_at <=).
    """
    conditions = [Call.client_id == current_user.id]

    if campaign_id:
        conditions.append(Call.campaign_id == uuid.UUID(campaign_id))
    if lead_status:
        conditions.append(Call.lead_status == lead_status.upper())
    if date_from:
        conditions.append(Call.started_at >= datetime.combine(date_from, datetime.min.time()).replace(tzinfo=timezone.utc))
    if date_to:
        conditions.append(Call.started_at <= datetime.combine(date_to, datetime.max.time()).replace(tzinfo=timezone.utc))

    offset = (page - 1) * page_size
    result = await db.execute(
        select(Call)
        .where(and_(*conditions))
        .order_by(Call.started_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    calls = result.scalars().all()

    return JSONResponse(
        content={
            "calls": [_call_dict(c) for c in calls],
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/{call_id}")
async def get_call(
    call_id: str,
    current_user: Client = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Return a single call record with full transcript."""
    result = await db.execute(select(Call).where(Call.id == uuid.UUID(call_id)))
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")
    if call.client_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return JSONResponse(content={"call": _call_dict(call)})


@router.get("/{call_id}/recording")
async def get_recording(
    call_id: str,
    current_user: Client = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """
    Generate a pre-signed R2 URL for the call recording and redirect to it.

    The URL expires after 1 hour.
    """
    result = await db.execute(select(Call).where(Call.id == uuid.UUID(call_id)))
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")
    if call.client_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if not call.recording_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recording not available for this call",
        )

    # If R2 is not configured, redirect directly to the Twilio recording URL
    if not settings.r2_enabled:
        return RedirectResponse(url=call.recording_url, status_code=status.HTTP_302_FOUND)

    # Derive the R2 object key from the stored URL or call_sid
    recording_url: str = call.recording_url
    public_url_prefix = (settings.r2_public_url or "").rstrip("/") + "/"

    if recording_url.startswith(public_url_prefix):
        object_key = recording_url.removeprefix(public_url_prefix)
    else:
        object_key = f"recordings/{call.call_sid}.mp3"

    r2 = _get_r2_client()
    signed_url: str = r2.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.r2_bucket_name, "Key": object_key},
        ExpiresIn=_R2_SIGNED_URL_EXPIRY,
    )

    return RedirectResponse(url=signed_url, status_code=status.HTTP_302_FOUND)
