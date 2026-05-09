"""Twilio and Razorpay webhook handlers, including real-time Media Stream WebSocket."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Form, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse, Response

from config import settings
from database import supabase_admin
from services.ai_pipeline import (
    AIConversation,
    generate_call_summary,
    start_conversation,
    mulaw_to_pcm,
    pcm_to_mulaw,
    pcm_to_wav,
)
from services.call_manager import schedule_callback_retry
from services.dnd_filter import add_to_blacklist
from services import wallet_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhooks"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _xml(content: str) -> Response:
    return Response(content=content, media_type="application/xml")


def _hangup_xml() -> Response:
    return _xml('<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>')


def _media_stream_xml(call_sid: str) -> Response:
    """Return TwiML that opens a bidirectional Media Stream WebSocket."""
    ws_url = f"{settings.backend_url.replace('https://', 'wss://').replace('http://', 'ws://')}/api/webhook/twilio/media-stream/{call_sid}"
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="{ws_url}" track="inbound_track">
      <Parameter name="call_sid" value="{call_sid}"/>
    </Stream>
  </Connect>
</Response>"""
    return _xml(xml)


# ---------------------------------------------------------------------------
# Twilio: Call Connected (fetched when recipient picks up)
# ---------------------------------------------------------------------------

@router.post("/twilio/call-connected")
async def twilio_call_connected(
    request: Request,
    campaign_id: str = Query(...),
    phone_number_id: str = Query(...),
    client_id: str = Query(...),
    call_id: str = Query(...),
    CallSid: str = Form(...),
    CallStatus: Optional[str] = Form(None),
) -> Response:
    """
    Twilio fetches this URL when the call connects.

    We verify wallet balance, initialise the AI conversation in Redis, then
    return TwiML that opens a bidirectional Media Stream WebSocket so we can
    run the real-time STT → Claude → TTS pipeline.
    """
    logger.info("Call connected: CallSid=%s campaign=%s", CallSid, campaign_id)

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
        return _hangup_xml()

    campaign = campaign_resp.data
    min_balance = settings.rate_per_min_paise * 2  # require at least 2 minutes

    if not await wallet_manager.has_sufficient_balance(client_id, min_balance):
        logger.warning("Insufficient balance for client %s — hanging up %s", client_id, CallSid)
        supabase_admin.table("campaigns").update({"status": "paused"}).eq("id", campaign_id).execute()
        return _hangup_xml()

    # Mark call as connected
    now = datetime.now(timezone.utc).isoformat()
    supabase_admin.table("calls").update({
        "call_sid": CallSid,
        "status": "connected",
        "started_at": now,
    }).eq("id", call_id).execute()

    # Increment attempt counter
    supabase_admin.table("phone_numbers").update({
        "status": "calling",
        "attempts": supabase_admin.table("phone_numbers")
            .select("attempts")
            .eq("id", phone_number_id)
            .single()
            .execute()
            .data.get("attempts", 0) + 1,
        "last_attempt_at": now,
    }).eq("id", phone_number_id).execute()

    # Initialise AI conversation state in Redis
    await start_conversation(
        call_sid=CallSid,
        system_prompt=campaign["system_prompt"],
        language=campaign["language"],
        agent_gender=campaign.get("agent_gender", "female"),
        campaign_id=campaign_id,
        phone_number_id=phone_number_id,
        client_id=client_id,
        call_id=call_id,
    )

    # Return TwiML — Twilio will open a WebSocket to our /media-stream/{call_sid} endpoint
    return _media_stream_xml(CallSid)


# ---------------------------------------------------------------------------
# Twilio: Media Stream WebSocket (real-time AI pipeline)
# ---------------------------------------------------------------------------

# Silence detection constants
_SAMPLE_RATE = 8000          # Twilio mulaw is always 8kHz
_SILENCE_THRESHOLD = 200     # RMS amplitude threshold (0-32767 range)
_SPEECH_MIN_CHUNKS = 5       # ~125ms of speech to start collecting
_SILENCE_CHUNKS_TO_END = 16  # ~400ms of silence after speech to trigger STT


@router.websocket("/twilio/media-stream/{call_sid}")
async def twilio_media_stream(websocket: WebSocket, call_sid: str) -> None:
    """
    Bidirectional Twilio Media Stream WebSocket handler.

    Audio protocol:
    - Twilio sends mulaw 8kHz, 20ms chunks (~160 bytes per chunk)
    - We accumulate chunks, detect speech, run STT → Claude → TTS
    - We send back mulaw audio frames to Twilio

    Message format (Twilio → server):
      {"event": "media", "streamSid": "...", "media": {"payload": "<base64 mulaw>"}}

    Message format (server → Twilio):
      {"event": "media", "streamSid": "...", "media": {"payload": "<base64 mulaw>"}}
      {"event": "clear", "streamSid": "..."}  # clears Twilio's audio buffer
    """
    await websocket.accept()
    logger.info("Media stream WebSocket opened for call_sid=%s", call_sid)

    stream_sid: Optional[str] = None
    conversation: Optional[AIConversation] = None

    # Audio accumulation buffers
    audio_buffer: list[bytes] = []       # raw mulaw chunks being collected
    speech_chunks: int = 0               # consecutive chunks above threshold
    silence_chunks: int = 0              # consecutive silent chunks after speech
    is_collecting: bool = False          # are we mid-utterance?
    processing_lock = asyncio.Lock()     # one pipeline run at a time
    is_processing: bool = False

    try:
        # Send opening greeting once conversation is loaded
        async def send_opening() -> None:
            nonlocal conversation
            conversation = await AIConversation.load_from_redis(call_sid)
            if not conversation:
                logger.error("No conversation state for call_sid=%s", call_sid)
                return
            audio_bytes = await conversation.get_opening_audio()
            await _send_audio(websocket, stream_sid, audio_bytes)

        async def process_speech(pcm_chunks: list[bytes]) -> None:
            nonlocal is_processing, conversation
            if is_processing or not conversation:
                return
            is_processing = True
            try:
                # Send filler sound immediately while pipeline runs
                filler_audio = await conversation.get_filler_audio(conversation.language)
                await _send_audio(websocket, stream_sid, filler_audio)

                # Concatenate PCM chunks and wrap in WAV for Sarvam STT
                pcm_data = b"".join(pcm_chunks)
                wav_data = pcm_to_wav(pcm_data, sample_rate=_SAMPLE_RATE)

                # STT → Claude → TTS
                response_audio = await conversation.process_utterance(wav_data)

                # Clear any buffered audio then play response
                if stream_sid:
                    await websocket.send_text(json.dumps({"event": "clear", "streamSid": stream_sid}))
                await _send_audio(websocket, stream_sid, response_audio)

                # Check if conversation should end
                if conversation.lead_status is not None:
                    logger.info(
                        "Call %s ending with lead_status=%s",
                        call_sid,
                        conversation.lead_status,
                    )
                    # Small delay so final audio plays before hang-up
                    await asyncio.sleep(3)
                    if stream_sid:
                        await websocket.send_text(
                            json.dumps({"event": "clear", "streamSid": stream_sid})
                        )
                    await websocket.close()
            except Exception as exc:
                logger.error("Pipeline error for call_sid=%s: %s", call_sid, exc)
            finally:
                is_processing = False

        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            event = msg.get("event")

            if event == "connected":
                # First message — stream hasn't started yet
                continue

            elif event == "start":
                stream_sid = msg["start"]["streamSid"]
                logger.info("Stream started: streamSid=%s call_sid=%s", stream_sid, call_sid)
                # Fire off opening greeting in background
                asyncio.create_task(send_opening())

            elif event == "media":
                if stream_sid is None:
                    continue
                payload_b64: str = msg["media"]["payload"]
                mulaw_chunk = base64.b64decode(payload_b64)
                pcm_chunk = mulaw_to_pcm(mulaw_chunk)

                # Silence detection via RMS amplitude
                rms = _rms(pcm_chunk)

                if rms > _SILENCE_THRESHOLD:
                    speech_chunks += 1
                    silence_chunks = 0
                    if speech_chunks >= _SPEECH_MIN_CHUNKS:
                        is_collecting = True
                else:
                    silence_chunks += 1
                    if is_collecting:
                        # Still collecting — keep a few silence frames for natural endings
                        if silence_chunks > _SILENCE_CHUNKS_TO_END:
                            # End of utterance detected
                            if audio_buffer and not is_processing:
                                chunks_to_process = list(audio_buffer)
                                audio_buffer.clear()
                                is_collecting = False
                                speech_chunks = 0
                                silence_chunks = 0
                                async with processing_lock:
                                    asyncio.create_task(process_speech(chunks_to_process))

                if is_collecting:
                    audio_buffer.append(pcm_chunk)

                # Safety: prevent unbounded buffer (~30 seconds max)
                if len(audio_buffer) > 1500:
                    audio_buffer.clear()
                    is_collecting = False
                    speech_chunks = 0

            elif event == "stop":
                logger.info("Stream stopped for call_sid=%s", call_sid)
                break

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for call_sid=%s", call_sid)
    except Exception as exc:
        logger.error("Media stream error for call_sid=%s: %s", call_sid, exc)
    finally:
        logger.info("Media stream closed for call_sid=%s", call_sid)


async def _send_audio(
    websocket: WebSocket,
    stream_sid: Optional[str],
    audio_bytes: bytes,
) -> None:
    """
    Send WAV/PCM audio to Twilio as mulaw chunks.

    Twilio expects mulaw encoded audio streamed in small frames,
    not one large blob.
    """
    if not stream_sid or not audio_bytes:
        return

    # Convert WAV → raw PCM → mulaw
    # If audio_bytes is already raw PCM (from Sarvam at 8kHz), skip WAV strip
    pcm = _strip_wav_header(audio_bytes)
    mulaw = pcm_to_mulaw(pcm)

    # Chunk into 160-byte frames (20ms at 8kHz)
    chunk_size = 160
    for i in range(0, len(mulaw), chunk_size):
        chunk = mulaw[i : i + chunk_size]
        payload = base64.b64encode(chunk).decode("ascii")
        await websocket.send_text(json.dumps({
            "event": "media",
            "streamSid": stream_sid,
            "media": {"payload": payload},
        }))


def _strip_wav_header(data: bytes) -> bytes:
    """Remove 44-byte WAV header if present, returning raw PCM."""
    if data[:4] == b"RIFF":
        return data[44:]
    return data


def _rms(pcm: bytes) -> float:
    """Compute RMS amplitude of 16-bit little-endian PCM data."""
    if len(pcm) < 2:
        return 0.0
    import struct
    n = len(pcm) // 2
    samples = struct.unpack(f"<{n}h", pcm[: n * 2])
    return (sum(s * s for s in samples) / n) ** 0.5


# ---------------------------------------------------------------------------
# Twilio: Call Status Callback
# ---------------------------------------------------------------------------

@router.post("/twilio/call-status")
async def twilio_call_status(
    CallSid: str = Form(...),
    CallStatus: str = Form(...),
    CallDuration: Optional[str] = Form("0"),
) -> JSONResponse:
    """
    Twilio calls this when call status changes (completed / failed / no-answer / busy).
    Handles cost deduction, summary generation, and lead tagging.
    """
    logger.info("Call status: CallSid=%s Status=%s Duration=%s", CallSid, CallStatus, CallDuration)

    duration_seconds = int(CallDuration or "0")

    call_resp = (
        supabase_admin.table("calls")
        .select("*")
        .eq("call_sid", CallSid)
        .single()
        .execute()
    )
    if not call_resp.data:
        logger.warning("No call record for CallSid=%s", CallSid)
        return JSONResponse(content={"ok": False})

    call = call_resp.data
    call_id = call["id"]
    client_id = call["client_id"]
    campaign_id = call["campaign_id"]
    phone_number_id = call["phone_number_id"]

    billable_minutes = math.ceil(duration_seconds / 60) if duration_seconds > 0 else 0
    cost_paise = billable_minutes * settings.rate_per_min_paise

    if cost_paise > 0:
        await wallet_manager.deduct(
            client_id=client_id,
            amount_paise=cost_paise,
            description=f"Call charge: {billable_minutes} min × ₹{settings.rate_per_min_paise / 100:.2f}/min",
            call_id=call_id,
        )

    # Recover transcript and lead_status from Redis conversation state
    conversation = await AIConversation.load_from_redis(CallSid)
    transcript: Optional[str] = None
    lead_status: Optional[str] = None

    if conversation:
        lines = []
        for msg in conversation.conversation_history:
            role = "Customer" if msg["role"] == "user" else "Agent"
            lines.append(f"{role}: {msg['content']}")
        transcript = "\n".join(lines) if lines else None
        lead_status = conversation.lead_status
        await conversation.delete_state()

    status_map = {
        "completed": "completed",
        "busy": "failed",
        "no-answer": "no_answer",
        "canceled": "failed",
        "failed": "failed",
    }
    final_status = status_map.get(CallStatus.lower(), "completed")
    now = datetime.now(timezone.utc).isoformat()

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
            goal = campaign_resp.data["goal"] if campaign_resp.data else "qualify"
            ai_summary = await generate_call_summary(transcript, goal)
        except Exception as exc:
            logger.error("Summary generation failed for call %s: %s", call_id, exc)

    supabase_admin.table("calls").update({
        "status": final_status,
        "duration_seconds": duration_seconds,
        "cost_paise": cost_paise,
        "transcript": transcript,
        "ai_summary": ai_summary,
        "lead_status": lead_status,
        "ended_at": now,
    }).eq("id", call_id).execute()

    pn_update: dict = {"status": "called"}
    if lead_status:
        pn_update["status"] = lead_status.lower()
    supabase_admin.table("phone_numbers").update(pn_update).eq("id", phone_number_id).execute()

    if lead_status == "CALLBACK":
        await schedule_callback_retry(phone_number_id, delay_seconds=3600)

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
            supabase_admin.table("whatsapp_alerts").insert({
                "id": str(uuid.uuid4()),
                "client_id": client_id,
                "campaign_id": campaign_id,
                "call_id": call_id,
                "phone_number": customer_number,
                "lead_status": lead_status,
                "ai_summary": ai_summary,
                "created_at": now,
                "sent": False,
            }).execute()
        except Exception as exc:
            logger.error("WhatsApp alert log failed for call %s: %s", call_id, exc)

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
                    reason="Wrong number reported during call",
                )
        except Exception as exc:
            logger.error("Blacklist insert failed for call %s: %s", call_id, exc)

    logger.info(
        "Call %s done: status=%s duration=%ds cost=%d paise lead=%s",
        call_id, final_status, duration_seconds, cost_paise, lead_status,
    )
    return JSONResponse(content={"ok": True})


# ---------------------------------------------------------------------------
# Twilio: Recording Status Callback
# ---------------------------------------------------------------------------

@router.post("/twilio/recording")
async def twilio_recording(
    CallSid: str = Form(...),
    RecordingUrl: Optional[str] = Form(None),
    RecordingStatus: Optional[str] = Form(None),
) -> JSONResponse:
    """Store the Twilio recording URL once transcription is complete."""
    if RecordingStatus != "completed" or not RecordingUrl:
        return JSONResponse(content={"ok": True})

    # Twilio recording URLs need .mp3 appended
    recording_url = f"{RecordingUrl}.mp3"

    supabase_admin.table("calls").update({
        "recording_url": recording_url,
    }).eq("call_sid", CallSid).execute()

    logger.info("Recording saved for CallSid=%s: %s", CallSid, recording_url)
    return JSONResponse(content={"ok": True})


# ---------------------------------------------------------------------------
# Razorpay: Payment Webhook
# ---------------------------------------------------------------------------

@router.post("/razorpay/payment")
async def razorpay_payment_webhook(
    request: Request,
    x_razorpay_signature: Optional[str] = Header(None),
) -> JSONResponse:
    """Verify Razorpay webhook signature and credit wallet on payment.captured."""
    raw_body = await request.body()

    if not x_razorpay_signature:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing signature")

    expected = hmac.new(
        key=settings.razorpay_key_secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, x_razorpay_signature):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")

    payload = json.loads(raw_body)
    event: str = payload.get("event", "")

    if event != "payment.captured":
        return JSONResponse(content={"ok": True, "event": event})

    payment_entity = payload["payload"]["payment"]["entity"]
    payment_id: str = payment_entity["id"]
    order_id: str = payment_entity.get("order_id", "")
    amount_paise: int = int(payment_entity["amount"])
    client_id: str = payment_entity.get("notes", {}).get("client_id", "")

    if not client_id:
        logger.warning("payment.captured missing client_id in notes; order_id=%s", order_id)
        return JSONResponse(content={"ok": False, "detail": "client_id not found"})

    await wallet_manager.credit(
        client_id=client_id,
        amount_paise=amount_paise,
        razorpay_payment_id=payment_id,
        description=f"Wallet top-up via Razorpay (payment: {payment_id})",
    )

    logger.info("Credited %d paise to client %s (payment=%s)", amount_paise, client_id, payment_id)
    return JSONResponse(content={"ok": True})
