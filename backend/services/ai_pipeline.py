"""Core AI conversation pipeline: STT → Claude → TTS per utterance."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import anthropic
import httpx

from config import settings
from database import supabase_admin

logger = logging.getLogger(__name__)

SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"
SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"
SARVAM_TIMEOUT = 10.0

CLAUDE_MODEL = "claude-sonnet-4-6"
MAX_CONVERSATION_TURNS = 30  # safety limit

# Mapping from campaign language to Sarvam language codes
_LANGUAGE_CODES: dict[str, str] = {
    "hindi": "hi-IN",
    "english": "en-IN",
    "bangla": "bn-IN",
    "tamil": "ta-IN",
}

# TTS speaker names (Sarvam AI speaker identifiers)
_TTS_SPEAKERS: dict[str, dict[str, str]] = {
    "hindi": {"male": "anand", "female": "anita"},
    "english": {"male": "arjun", "female": "diya"},
    "bangla": {"male": "arjun", "female": "diya"},
    "tamil": {"male": "arjun", "female": "diya"},
}

# Pre-defined filler audio phrases per language (text that will be TTS'd on demand)
_FILLER_TEXT: dict[str, str] = {
    "hindi": "haan...",
    "english": "sure...",
    "bangla": "haan...",
    "tamil": "sari...",
}

END_OF_CALL_MARKERS = frozenset(
    ["INTERESTED", "NOT_INTERESTED", "CALLBACK", "WRONG_NUMBER", "LANGUAGE_BARRIER", "TRANSFER"]
)

_anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _get_redis():
    """Import redis_client lazily to avoid circular import at module load time."""
    from main import redis_client
    return redis_client


class AIConversation:
    """
    Manages one AI conversation tied to a single Exotel call.

    State is persisted in Redis so that webhook handlers across multiple
    requests can resume the same conversation.
    """

    def __init__(
        self,
        call_sid: str,
        system_prompt: str,
        language: str,
        campaign_id: str,
        phone_number_id: str,
        client_id: str,
    ) -> None:
        self.call_sid = call_sid
        self.system_prompt = system_prompt
        self.language = language
        self.campaign_id = campaign_id
        self.phone_number_id = phone_number_id
        self.client_id = client_id
        self.conversation_history: list[dict] = []
        self.lead_status: Optional[str] = None
        self.call_id: Optional[str] = None
        self._redis_key = f"conversation:{call_sid}"

    # ------------------------------------------------------------------
    # Redis persistence
    # ------------------------------------------------------------------

    async def save_state(self) -> None:
        """Serialize conversation state to Redis with a 1-hour TTL."""
        state = {
            "call_sid": self.call_sid,
            "system_prompt": self.system_prompt,
            "language": self.language,
            "campaign_id": self.campaign_id,
            "phone_number_id": self.phone_number_id,
            "client_id": self.client_id,
            "conversation_history": self.conversation_history,
            "lead_status": self.lead_status,
            "call_id": self.call_id,
        }
        redis = _get_redis()
        await redis.set(self._redis_key, json.dumps(state), ex=3600)

    @classmethod
    async def load_from_redis(cls, call_sid: str) -> Optional["AIConversation"]:
        """
        Load conversation state from Redis.

        Returns:
            An AIConversation instance, or None if not found.
        """
        redis = _get_redis()
        raw = await redis.get(f"conversation:{call_sid}")
        if raw is None:
            return None

        state = json.loads(raw)
        obj = cls(
            call_sid=state["call_sid"],
            system_prompt=state["system_prompt"],
            language=state["language"],
            campaign_id=state["campaign_id"],
            phone_number_id=state["phone_number_id"],
            client_id=state["client_id"],
        )
        obj.conversation_history = state["conversation_history"]
        obj.lead_status = state["lead_status"]
        obj.call_id = state["call_id"]
        return obj

    async def delete_state(self) -> None:
        """Remove conversation state from Redis after call ends."""
        redis = _get_redis()
        await redis.delete(self._redis_key)

    # ------------------------------------------------------------------
    # Sarvam AI integrations
    # ------------------------------------------------------------------

    async def _stt(self, audio_bytes: bytes) -> str:
        """
        Convert audio bytes to text using Sarvam AI STT.

        Args:
            audio_bytes: Raw audio data (WAV/OGG format).

        Returns:
            Transcribed text string.
        """
        lang_code = _LANGUAGE_CODES.get(self.language, "hi-IN")
        async with httpx.AsyncClient(timeout=SARVAM_TIMEOUT) as client:
            response = await client.post(
                SARVAM_STT_URL,
                headers={"api-subscription-key": settings.sarvam_api_key},
                files={"file": ("audio.wav", audio_bytes, "audio/wav")},
                data={"language_code": lang_code, "model": "saarika:v1"},
            )
            response.raise_for_status()
            result = response.json()
            transcript: str = result.get("transcript", "")
            logger.debug("STT result: %r", transcript[:100])
            return transcript

    async def _tts(self, text: str, gender: str = "female") -> bytes:
        """
        Convert text to audio using Sarvam AI TTS.

        Args:
            text: Text to synthesize.
            gender: "male" or "female" speaker voice.

        Returns:
            Audio bytes (WAV format).
        """
        lang_code = _LANGUAGE_CODES.get(self.language, "hi-IN")
        speakers = _TTS_SPEAKERS.get(self.language, _TTS_SPEAKERS["english"])
        speaker = speakers.get(gender, speakers["female"])

        async with httpx.AsyncClient(timeout=SARVAM_TIMEOUT) as client:
            response = await client.post(
                SARVAM_TTS_URL,
                headers={
                    "api-subscription-key": settings.sarvam_api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "inputs": [text],
                    "target_language_code": lang_code,
                    "speaker": speaker,
                    "pitch": 0,
                    "pace": 1.0,
                    "loudness": 1.5,
                    "speech_sample_rate": 8000,
                    "enable_preprocessing": True,
                    "model": "bulbul:v1",
                },
            )
            response.raise_for_status()
            result = response.json()
            # Sarvam returns base64-encoded audio
            import base64
            audio_b64: str = result["audios"][0]
            return base64.b64decode(audio_b64)

    # ------------------------------------------------------------------
    # Claude AI
    # ------------------------------------------------------------------

    async def _get_claude_response(self, user_text: str) -> str:
        """
        Send the latest utterance to Claude and get the agent's reply.

        Args:
            user_text: Transcribed customer utterance.

        Returns:
            Agent response text (may contain end-of-call marker as last line).
        """
        self.conversation_history.append({"role": "user", "content": user_text})

        # Safety: trim history to avoid token overflow
        history = self.conversation_history[-MAX_CONVERSATION_TURNS * 2:]

        full_response = ""
        with _anthropic_client.messages.stream(
            model=CLAUDE_MODEL,
            max_tokens=512,
            system=self.system_prompt,
            messages=history,
        ) as stream:
            for text_chunk in stream.text_stream:
                full_response += text_chunk

        self.conversation_history.append({"role": "assistant", "content": full_response})
        logger.debug("Claude response: %r", full_response[:120])
        return full_response

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process_utterance(self, audio_bytes: bytes) -> bytes:
        """
        Full STT → Claude → TTS pipeline for one customer utterance.

        1. Transcribe audio with Sarvam STT.
        2. Append to conversation history.
        3. Stream Claude response.
        4. Detect end-of-call marker.
        5. Synthesize agent reply with Sarvam TTS.
        6. Persist updated state to Redis.

        Args:
            audio_bytes: Raw audio from the customer's utterance.

        Returns:
            Audio bytes of the agent's reply.
        """
        # Step 1: STT
        user_text = await self._stt(audio_bytes)
        if not user_text.strip():
            logger.warning("Empty STT result for call_sid=%s", self.call_sid)
            filler = await self.get_filler_audio(self.language)
            return filler

        # Steps 2–3: Claude
        agent_response = await self._get_claude_response(user_text)

        # Step 4: Check for end-of-call marker
        lines = agent_response.strip().splitlines()
        last_line = lines[-1].strip() if lines else ""
        if last_line in END_OF_CALL_MARKERS:
            self.lead_status = last_line
            # Strip the marker from spoken text
            spoken_text = "\n".join(lines[:-1]).strip()
        else:
            spoken_text = agent_response.strip()

        # Step 5: TTS
        audio_response = await self._tts(spoken_text)

        # Step 6: Save state
        await self.save_state()

        return audio_response

    async def get_filler_audio(self, language: str) -> bytes:
        """
        Return a pre-synthesized short filler phrase for the given language.

        This is played while the STT/Claude pipeline processes to avoid silence.

        Args:
            language: Campaign language key.

        Returns:
            Audio bytes of the filler phrase.
        """
        filler_text = _FILLER_TEXT.get(language, _FILLER_TEXT["english"])
        return await self._tts(filler_text)

    async def get_opening_audio(self) -> bytes:
        """
        Generate and return the agent's opening greeting.

        The greeting is constructed from the system prompt context and sent
        as the first message in the conversation.

        Returns:
            Audio bytes of the opening greeting.
        """
        opening_prompt = (
            "Start the call now. Greet the customer, introduce yourself and your company "
            "in one or two sentences, then state the brief reason for calling. Keep it under 20 seconds."
        )
        agent_response = await self._get_claude_response(opening_prompt)

        lines = agent_response.strip().splitlines()
        last_line = lines[-1].strip() if lines else ""
        if last_line in END_OF_CALL_MARKERS:
            self.lead_status = last_line
            spoken_text = "\n".join(lines[:-1]).strip()
        else:
            spoken_text = agent_response.strip()

        audio = await self._tts(spoken_text)
        await self.save_state()
        return audio

    async def end_conversation(self, lead_status: str) -> None:
        """
        Finalise the conversation: persist transcript and update DB records.

        Args:
            lead_status: Final classification (INTERESTED, NOT_INTERESTED, etc.).
        """
        self.lead_status = lead_status

        # Build plain-text transcript
        transcript_lines = []
        for msg in self.conversation_history:
            role = "Customer" if msg["role"] == "user" else "Agent"
            transcript_lines.append(f"{role}: {msg['content']}")
        transcript_text = "\n".join(transcript_lines)

        now = datetime.now(timezone.utc).isoformat()

        if self.call_id:
            supabase_admin.table("calls").update(
                {
                    "transcript": transcript_text,
                    "lead_status": lead_status,
                    "status": "completed",
                    "ended_at": now,
                }
            ).eq("id", self.call_id).execute()

        supabase_admin.table("phone_numbers").update(
            {
                "status": "called",
                "lead_status": lead_status,
            }
        ).eq("id", self.phone_number_id).execute()

        await self.delete_state()
        logger.info(
            "Conversation ended: call_sid=%s, lead_status=%s", self.call_sid, lead_status
        )


async def start_conversation(
    call_sid: str,
    system_prompt: str,
    language: str,
    campaign_id: str,
    phone_number_id: str,
    client_id: str,
    call_id: str,
) -> AIConversation:
    """
    Initialise and persist a new AIConversation for a just-connected call.

    Args:
        call_sid: Exotel CallSid.
        system_prompt: Pre-built prompt from prompt_builder.
        language: Campaign language key.
        campaign_id: UUID.
        phone_number_id: UUID.
        client_id: UUID.
        call_id: UUID of the call record in DB.

    Returns:
        The newly created AIConversation instance.
    """
    conv = AIConversation(
        call_sid=call_sid,
        system_prompt=system_prompt,
        language=language,
        campaign_id=campaign_id,
        phone_number_id=phone_number_id,
        client_id=client_id,
    )
    conv.call_id = call_id
    await conv.save_state()
    logger.info("Started conversation for call_sid=%s", call_sid)
    return conv


async def generate_call_summary(transcript: str, campaign_goal: str) -> str:
    """
    Use Claude to generate a brief AI summary of a completed call transcript.

    Args:
        transcript: Full call transcript.
        campaign_goal: The campaign's goal key for context.

    Returns:
        A short summary string (2-4 sentences).
    """
    prompt = (
        f"Below is a sales call transcript for a campaign with goal: {campaign_goal}.\n\n"
        f"{transcript}\n\n"
        "Write a concise 2-4 sentence summary covering: "
        "(1) customer's interest level, "
        "(2) key objections or concerns raised, "
        "(3) outcome/next steps. "
        "Be factual and objective."
    )

    message = _anthropic_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()
