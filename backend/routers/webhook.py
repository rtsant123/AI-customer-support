"""Exotel and Razorpay webhook handlers."""

from __future__ import annotations

import hashlib
import hmac
import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Form, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response

from config import settings
from database import supabase_admin
from services.ai_pipeline import (
    AIConversation,
    generate_call_summary,
    start_conversation,
)
from services.call_manager import schedule_callback_retry
from services.dnd_filter import add_to_blacklist
from services import wallet_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhooks"])

_CALL_CONNECT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>{greeting}</Say>
</Response>"""

_TRANSFER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Dial>{transfer_number}</Dial>
</Response>"""


def _xml_response(content: str) -> Response:
    return Response(content=content, media_type="application/xml")


# ---------------------------------------------------------------------------
# Exotel: Call Connected
# ---------------------------------------------------------------------------

@router.post("/exotel/call-connected")
async def exotel_call_connected(
    CallSid: str = Form(...),
    From: str = Form(...),
    To: str = Form(...),
    Direction: Optional[str] = Form(None),
    Status: Optional[str] = Form(None),
) -> Response:
    """
    Handle Exotel's call-connected webhook.

    Called when the recipient picks up. We:
    1. Look up the phone_number record by the dialled number.
    2. Fetch campaign + system_prompt.
    3. Verify the client has sufficient wallet balance.
    4. Create/link the call record.
    5. Start the AI conversation and return opening audio as TwiML/XML.
    """
    logger.info("Call connected: CallSid=%s From=%s To=%s", CallSid, From, To)

    # Normalize: Exotel's "To" is the customer number
    customer_number = To if Direction != "outbound" else From

    # Find phone_number record
    pn_resp = (
        supabase_admin.table("phone_numbers")
        .select("id, campaign_id, client_id, number")
        .eq("number", customer_number)
        .eq("status", "calling")
        .order("last_attempt_at", desc=True)
        .limit(1)
        .execute()
    )
    if not pn_resp.data:
        logger.warning("No phone_number record found for %s (CallSid=%s)", customer_number, CallSid)
        return _xml_response(
            '<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>'
        )

    pn = pn_resp.data[0]
    phone_number_id = pn["id"]
    campaign_id = pn["campaign_id"]
    client_id = pn["client_id"]

    # Load campaign
    campaign_resp = (
        supabase_admin.table("campaigns")
        .select("*")
        .eq("id", campaign_id)
        .single()
        .execute()
    )
    if not campaign_resp.data:
        logger.error("Campaign %s not found for CallSid=%s", campaign_id, CallSid)
        return _xml_response(
            '<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>'
        )

    campaign = campaign_resp.data
    system_prompt: str = campaign["system_prompt"]
    language: str = campaign["language"]

    # Check wallet balance (minimum 2 minutes = 2 * rate)
    min_balance = settings.rate_per_min_paise * 2
    if not await wallet_manager.has_sufficient_balance(client_id, min_balance):
        logger.warning("Insufficient balance for client %s — hanging up call %s", client_id, CallSid)
        # Pause the campaign to avoid wasting calls
        supabase_admin.table("campaigns").update({"status": "paused"}).eq(
            "id", campaign_id
        ).execute()
        return _xml_response(
            '<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>'
        )

    # Find or create call record (call_manager.initiate_call already created one)
    call_resp = (
        supabase_admin.table("calls")
        .select("id")
        .eq("call_sid", CallSid)
        .single()
        .execute()
    )
    if call_resp.data:
        call_id = call_resp.data["id"]
        # Mark as in-progress
        supabase_admin.table("calls").update({"status": "in_progress"}).eq(
            "id", call_id
        ).execute()
    else:
        # Fallback: create a new call record
        call_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        supabase_admin.table("calls").insert(
            {
                "id": call_id,
                "campaign_id": campaign_id,
                "phone_number_id": phone_number_id,
                "client_id": client_id,
                "call_sid": CallSid,
                "status": "in_progress",
                "started_at": now,
            }
        ).execute()

    # Increment attempt counter via RPC (atomic increment in DB)
    supabase_admin.rpc("increment_phone_number_attempts", {"row_id": phone_number_id}).execute()

    # Start the AI conversation state in Redis
    await start_conversation(
        call_sid=CallSid,
        system_prompt=system_prompt,
        language=language,
        campaign_id=campaign_id,
        phone_number_id=phone_number_id,
        client_id=client_id,
        call_id=call_id,
    )

    logger.info("AI conversation started for CallSid=%s, call_id=%s", CallSid, call_id)

    # Return initial XML — Exotel streams audio back via subsequent webhooks.
    # We return a <Say> greeting as a placeholder; in a full deployment
    # with Exotel's streaming API this would be a <Stream> verb.
    greeting = (
        "नमस्ते" if language == "hindi"
        else "Namaskar" if language == "bangla"
        else "Vanakkam" if language == "tamil"
        else "Hello"
    )
    xml_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="{_tts_lang_code(language)}">{greeting}</Say>
    <Pause length="1"/>
</Response>"""
    return _xml_response(xml_body)


def _tts_lang_code(language: str) -> str:
    return {
        "hindi": "hi-IN",
        "english": "en-IN",
        "bangla": "bn-IN",
        "tamil": "ta-IN",
    }.get(language, "en-IN")


# ---------------------------------------------------------------------------
# Exotel: Call Completed
# ---------------------------------------------------------------------------

@router.post("/exotel/call-completed")
async def exotel_call_completed(
    CallSid: str = Form(...),
    Status: str = Form(...),
    Duration: Optional[str] = Form("0"),
    RecordingUrl: Optional[str] = Form(None),
) -> JSONResponse:
    """
    Handle Exotel's call-completed webhook.

    Responsibilities:
    - Calculate and deduct call cost from wallet.
    - Update call record with duration, cost, recording URL, status.
    - Generate AI summary of transcript.
    - Update phone_number lead_status.
    - Schedule CALLBACK retries if applicable.
    - Log INTERESTED leads for WhatsApp notification.
    """
    logger.info("Call completed: CallSid=%s Status=%s Duration=%s", CallSid, Status, Duration)

    duration_seconds = int(Duration or "0")

    # Load call record
    call_resp = (
        supabase_admin.table("calls")
        .select("*")
        .eq("call_sid", CallSid)
        .single()
        .execute()
    )
    if not call_resp.data:
        logger.warning("No call record for CallSid=%s", CallSid)
        return JSONResponse(content={"ok": False, "detail": "Call not found"})

    call = call_resp.data
    call_id = call["id"]
    client_id = call["client_id"]
    campaign_id = call["campaign_id"]
    phone_number_id = call["phone_number_id"]

    # Calculate cost: ceil(duration / 60) minutes × rate
    billable_minutes = math.ceil(duration_seconds / 60) if duration_seconds > 0 else 0
    cost_paise = billable_minutes * settings.rate_per_min_paise

    # Deduct from wallet
    if cost_paise > 0:
        deducted = await wallet_manager.deduct(
            client_id=client_id,
            amount_paise=cost_paise,
            description=f"Call charge: {billable_minutes} min × ₹{settings.rate_per_min_paise / 100:.2f}/min",
            call_id=call_id,
        )
        if not deducted:
            logger.warning("Could not deduct %d paise for call %s — insufficient balance", cost_paise, call_id)

    # Recover conversation state for transcript and lead_status
    conversation = await AIConversation.load_from_redis(CallSid)
    transcript: Optional[str] = None
    lead_status: Optional[str] = None

    if conversation:
        # Build transcript from history
        lines = []
        for msg in conversation.conversation_history:
            role = "Customer" if msg["role"] == "user" else "Agent"
            lines.append(f"{role}: {msg['content']}")
        transcript = "\n".join(lines) if lines else None
        lead_status = conversation.lead_status
        await conversation.delete_state()
    else:
        logger.warning("No Redis conversation state found for CallSid=%s", CallSid)

    # Map Exotel call status to our statuses
    call_status_map = {
        "completed": "completed",
        "busy": "failed",
        "no-answer": "no_answer",
        "canceled": "failed",
        "failed": "failed",
    }
    final_status = call_status_map.get(Status.lower(), "completed")

    now = datetime.now(timezone.utc).isoformat()

    # Generate AI summary if we have a transcript
    ai_summary: Optional[str] = None
    if transcript:
        try:
            campaign_resp = (
                supabase_admin.table("campaigns")
                .select("goal")
                .eq("id", campaign_id)
                .single()
                .execute()
            )
            campaign_goal = campaign_resp.data["goal"] if campaign_resp.data else "qualify"
            ai_summary = await generate_call_summary(transcript, campaign_goal)
        except Exception as exc:
            logger.error("AI summary generation failed for call %s: %s", call_id, exc)

    # Update call record
    supabase_admin.table("calls").update(
        {
            "status": final_status,
            "duration_seconds": duration_seconds,
            "cost_paise": cost_paise,
            "recording_url": RecordingUrl,
            "transcript": transcript,
            "ai_summary": ai_summary,
            "lead_status": lead_status,
            "ended_at": now,
        }
    ).eq("id", call_id).execute()

    # Update phone_number status
    pn_update: dict = {"status": "called"}
    if lead_status:
        pn_update["lead_status"] = lead_status
    supabase_admin.table("phone_numbers").update(pn_update).eq("id", phone_number_id).execute()

    # Handle CALLBACK: schedule retry in 1 hour
    if lead_status == "CALLBACK":
        await schedule_callback_retry(phone_number_id, delay_seconds=3600)
        logger.info("Scheduled callback retry for phone_number_id=%s", phone_number_id)

    # Handle INTERESTED: log for WhatsApp alert (insert to whatsapp_alerts table)
    if lead_status == "INTERESTED":
        try:
            pn_resp = (
                supabase_admin.table("phone_numbers")
                .select("number")
                .eq("id", phone_number_id)
                .single()
                .execute()
            )
            customer_number = pn_resp.data["number"] if pn_resp.data else "unknown"

            supabase_admin.table("whatsapp_alerts").insert(
                {
                    "id": str(uuid.uuid4()),
                    "client_id": client_id,
                    "campaign_id": campaign_id,
                    "call_id": call_id,
                    "phone_number": customer_number,
                    "lead_status": lead_status,
                    "ai_summary": ai_summary,
                    "created_at": now,
                    "sent": False,
                }
            ).execute()
            logger.info("WhatsApp alert logged for INTERESTED lead: %s", customer_number)
        except Exception as exc:
            logger.error("Failed to log WhatsApp alert for call %s: %s", call_id, exc)

    # Handle WRONG_NUMBER or repeated NOT_INTERESTED: blacklist
    if lead_status == "WRONG_NUMBER":
        try:
            pn_resp = (
                supabase_admin.table("phone_numbers")
                .select("number")
                .eq("id", phone_number_id)
                .single()
                .execute()
            )
            if pn_resp.data:
                await add_to_blacklist(
                    client_id=client_id,
                    phone_number=pn_resp.data["number"],
                    reason="Wrong number — reported during call",
                )
        except Exception as exc:
            logger.error("Failed to blacklist wrong number for call %s: %s", call_id, exc)

    logger.info(
        "Call %s completed: status=%s, duration=%ds, cost=%d paise, lead_status=%s",
        call_id,
        final_status,
        duration_seconds,
        cost_paise,
        lead_status,
    )

    return JSONResponse(content={"ok": True})


# ---------------------------------------------------------------------------
# Razorpay: Payment Webhook
# ---------------------------------------------------------------------------

@router.post("/razorpay/payment")
async def razorpay_payment_webhook(
    request: Request,
    x_razorpay_signature: Optional[str] = Header(None),
) -> JSONResponse:
    """
    Handle Razorpay payment webhooks.

    Verifies the webhook signature and credits the client wallet on
    payment.captured events.
    """
    raw_body = await request.body()

    if not x_razorpay_signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Razorpay-Signature header",
        )

    # Verify signature
    webhook_secret = settings.razorpay_key_secret
    expected = hmac.new(
        key=webhook_secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, x_razorpay_signature):
        logger.warning("Invalid Razorpay webhook signature")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature",
        )

    import json

    payload = json.loads(raw_body)
    event: str = payload.get("event", "")

    if event != "payment.captured":
        # Acknowledge events we don't handle
        return JSONResponse(content={"ok": True, "event": event})

    payment_entity = payload["payload"]["payment"]["entity"]
    payment_id: str = payment_entity["id"]
    order_id: str = payment_entity.get("order_id", "")
    amount_paise: int = int(payment_entity["amount"])
    payment_notes: dict = payment_entity.get("notes", {})
    client_id: str = payment_notes.get("client_id", "")

    if not client_id:
        # Try to look up by order_id via pending topup records
        logger.warning("payment.captured has no client_id in notes; order_id=%s", order_id)
        return JSONResponse(content={"ok": False, "detail": "client_id not found in notes"})

    await wallet_manager.credit(
        client_id=client_id,
        amount_paise=amount_paise,
        razorpay_payment_id=payment_id,
        description=f"Wallet top-up via Razorpay webhook (payment: {payment_id})",
    )

    logger.info(
        "Razorpay webhook: credited %d paise to client %s (payment=%s)",
        amount_paise,
        client_id,
        payment_id,
    )
    return JSONResponse(content={"ok": True})
