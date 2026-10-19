"""Fallback voice pipeline (ADDENDUM-01 section 5.5): raw audio in, text out via Groq Whisper; one sentence in,
WAV out via Groq TTS. When TTS is unavailable the response says so and the browser uses speechSynthesis."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from backend.config import settings
from backend.providers.retry import ProviderError
from backend.routes.deps import require

router = APIRouter()
log = logging.getLogger("hello_campus.speech")
EXTENSIONS = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/mpeg": "mp3",
              "audio/wav": "wav", "audio/x-wav": "wav"}


class SpeechText(BaseModel):
    text: str = Field(min_length=1, max_length=settings.speech_max_text_chars)

    @field_validator("text")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Text is empty")
        return value.strip()


class TranscriptOut(BaseModel):
    text: str
    language: str


class SpeechConfig(BaseModel):
    live_enabled: bool
    server_tts: bool
    sentence_max_chars: int
    recording_max_ms: int


@router.get("/api/speech/config", response_model=SpeechConfig)
def speech_config() -> SpeechConfig:
    return SpeechConfig(live_enabled=settings.live_enabled, server_tts=settings.server_tts_enabled,
                        sentence_max_chars=settings.speech_max_text_chars,
                        recording_max_ms=int(settings.speech_recording_limit_s * 1000))


@router.post("/api/stt", response_model=TranscriptOut)
async def transcribe(request: Request, llm=Depends(require("llm"))) -> TranscriptOut:
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > settings.speech_max_audio_bytes:
            raise HTTPException(413, "This recording is too large. Please record a shorter question.")
    if not content:
        raise HTTPException(422, "The recording is empty")
    mime = (request.headers.get("content-type") or "audio/webm").split(";")[0].strip()
    try:
        t = await llm.transcribe(bytes(content), f"speech.{EXTENSIONS.get(mime, 'webm')}", mime)
    except ProviderError as exc:
        log.warning("stt failed: %s", exc)
        raise HTTPException(503, f"{exc.user_message} You can type your question instead.") from exc
    if not t.text:
        raise HTTPException(422, "I couldn't hear anything. Please try again a little closer to the mic.")
    return TranscriptOut(text=t.text, language=t.language)


@router.post("/api/tts")
async def synthesize(body: SpeechText, llm=Depends(require("llm"))) -> Response:
    if not settings.server_tts_enabled:
        raise HTTPException(503, "Server voice is off, using the browser voice.")
    try:
        audio = await llm.speak(body.text)
    except ProviderError as exc:
        log.warning("tts failed: %s", exc)
        raise HTTPException(503, "Server voice is unavailable, using the browser voice.") from exc
    return Response(audio, media_type="audio/wav", headers={"Cache-Control": "no-store"})
