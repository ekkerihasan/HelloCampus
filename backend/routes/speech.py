"""Raw audio in, text out; one sentence in, WAV out. CPU calls run in workers."""
import asyncio
import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from backend.config import settings
from backend.routes.deps import require

router = APIRouter()
log = logging.getLogger("hello_campus.speech")
T = TypeVar("T")


class SpeechWorker:
    """One admitted job per model, with no queue of stale recordings/sentences.

    The concurrent future owns the slot. Cancelling an ASGI coroutine cannot
    release a slot while its underlying CPU thread is still running.
    """

    def __init__(self, name: str):
        self.name = name
        self._slot = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"speech-{name}")

    def submit(self, function: Callable[[], T]) -> Future[T]:
        if not self._slot.acquire(blocking=False):
            raise HTTPException(503, f"Local {self.name} is busy finishing a previous request. Please try again shortly.")
        try:
            future = self._executor.submit(function)
        except BaseException:
            self._slot.release()
            raise
        future.add_done_callback(lambda _: self._slot.release())
        return future


_workers = {name: SpeechWorker(name) for name in ("stt", "tts")}


async def _wait_for_disconnect(request: Request) -> None:
    # Both endpoints consume their entire request bodies before starting work.
    # Awaiting the remaining ASGI receive detects disconnects without polling.
    while True:
        if (await request.receive())["type"] == "http.disconnect":
            return


async def _infer(request: Request, name: str, function: Callable[[], T]) -> T:
    if await request.is_disconnected():
        raise HTTPException(503, "Speech request was disconnected before inference started.")
    future = _workers[name].submit(function)
    wrapped = asyncio.wrap_future(future)
    disconnected = asyncio.create_task(_wait_for_disconnect(request))
    try:
        done, _ = await asyncio.wait({wrapped, disconnected}, return_when=asyncio.FIRST_COMPLETED)
        if disconnected in done:
            # Cancellation succeeds for a not-yet-started job. A running job
            # keeps the slot until the concurrent future actually completes.
            raise HTTPException(503, "Speech request was disconnected. Please try again when ready.")
        return await wrapped
    finally:
        # Cancel the concurrent future directly, before an event-loop callback
        # could allow an executor-queued job to begin after cancellation.
        if not future.done():
            future.cancel()
        if not wrapped.done():
            wrapped.cancel()
        elif not wrapped.cancelled():
            wrapped.exception()  # consume errors when completion races a disconnect
        disconnected.cancel()
        await asyncio.gather(disconnected, return_exceptions=True)


class SpeechText(BaseModel):
    text: str = Field(min_length=1, max_length=settings.speech_max_text_chars)

    @field_validator("text")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Text is empty")
        return value.strip()


class Transcript(BaseModel):
    text: str
    language: str
    ms: int


class SpeechConfig(BaseModel):
    recording_max_ms: int
    sentence_max_chars: int


@router.get("/api/speech/config", response_model=SpeechConfig)
def speech_config() -> SpeechConfig:
    return SpeechConfig(
        recording_max_ms=int(min(settings.speech_recording_limit_s, settings.speech_max_duration_s) * 1000),
        sentence_max_chars=min(settings.speech_sentence_chars, settings.speech_max_text_chars),
    )


@router.post("/api/stt", response_model=Transcript)
async def transcribe(request: Request, stt=Depends(require("stt"))):
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > settings.speech_max_audio_bytes:
            raise HTTPException(413, "This recording is too large. Please record a shorter question.")
    if not content:
        raise HTTPException(422, "The recording is empty")
    try:
        return await _infer(request, "stt", lambda: stt.transcribe(bytes(content)))
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        log.exception("Local speech recognition failed")
        raise HTTPException(503, "Speech recognition failed. Please try again or type your question.") from exc


@router.post("/api/tts")
async def synthesize(body: SpeechText, request: Request, tts=Depends(require("tts"))):
    try:
        audio = await _infer(request, "tts", lambda: tts.synthesize(body.text))
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("Local speech synthesis failed")
        raise HTTPException(503, "Speech playback failed. You can still read the answer.") from exc
    return Response(audio, media_type="audio/wav", headers={"Cache-Control": "no-store"})
