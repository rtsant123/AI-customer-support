"""Call history and recording routes."""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import boto3
from botocore.config import Config
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse, RedirectResponse

from config import settings
from database import supabase_admin
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


@router.get("")
async def list_calls(
    campaign_id: Optional[str] = Query(None),
    lead_status: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """
    List calls for the current client with optional filters.

    Filters: campaign_id, lead_status, date_from (started_at >=), date_to (started_at <=).
    """
    query = (
        supabase_admin.table("calls")
        .select("*")
        .eq("client_id", current_user["id"])
        .order("started_at", desc=True)
    )

    if campaign_id:
        query = query.eq("campaign_id", campaign_id)
    if lead_status:
        query = query.eq("lead_status", lead_status.upper())
    if date_from:
        query = query.gte("started_at", date_from.isoformat())
    if date_to:
        # Include the full day_to
        query = query.lte("started_at", f"{date_to.isoformat()}T23:59:59")

    offset = (page - 1) * page_size
    query = query.range(offset, offset + page_size - 1)

    response = query.execute()
    return JSONResponse(
        content={
            "calls": response.data or [],
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/{call_id}")
async def get_call(
    call_id: str,
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Return a single call record with full transcript."""
    response = (
        supabase_admin.table("calls")
        .select("*")
        .eq("id", call_id)
        .single()
        .execute()
    )
    call = response.data
    if not call:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")
    if call["client_id"] != current_user["id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return JSONResponse(content={"call": call})


@router.get("/{call_id}/recording")
async def get_recording(
    call_id: str,
    current_user: dict = Depends(get_current_user),
) -> RedirectResponse:
    """
    Generate a pre-signed R2 URL for the call recording and redirect to it.

    The URL expires after 1 hour.
    """
    call_response = (
        supabase_admin.table("calls")
        .select("client_id, recording_url, call_sid")
        .eq("id", call_id)
        .single()
        .execute()
    )
    call = call_response.data
    if not call:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")
    if call["client_id"] != current_user["id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if not call.get("recording_url"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recording not available for this call",
        )

    # Derive the R2 object key from the stored URL or call_sid
    recording_url: str = call["recording_url"]
    public_url_prefix = settings.r2_public_url.rstrip("/") + "/"

    if recording_url.startswith(public_url_prefix):
        object_key = recording_url.removeprefix(public_url_prefix)
    else:
        # Fallback: use call_sid as key
        object_key = f"recordings/{call['call_sid']}.mp3"

    r2 = _get_r2_client()
    signed_url: str = r2.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.r2_bucket_name, "Key": object_key},
        ExpiresIn=_R2_SIGNED_URL_EXPIRY,
    )

    return RedirectResponse(url=signed_url, status_code=status.HTTP_302_FOUND)
