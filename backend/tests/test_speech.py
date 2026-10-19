"""Speech contracts and failures use controlled doubles, never load model weights."""
import asyncio
import io
import threading
import wave
from types import SimpleNamespace

from fastapi import FastAPI
import httpx
import pytest

from backend.config import settings
from backend.routes.speech import router
from backend.speech.stt import SpeechToText
from backend.status import registry


class FakeSTT:
    def __init__(self):
        self.received = None
        self.thread = None
        self.error = None

    def transcribe(self, audio):
        self.received = audio
        self.thread = threading.get_ident()
        if self.error:
            raise self.error
        return {"text": "Test question", "language": "en", "ms": 12}


class FakeTTS:
    def __init__(self):
        self.received = None
        self.thread = None
        self.error = None

    def synthesize(self, text):
        self.received = text
        self.thread = threading.get_ident()
        if self.error:
            raise self.error
        return wav_bytes(0.5)


def wav_bytes(seconds):
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\0\0" * int(16000 * seconds))
    return output.getvalue()


@pytest.fixture
async def speech_api(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    services = {"stt": FakeSTT(), "tts": FakeTTS()}
    monkeypatch.setattr(registry, "get", services.get)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, services


async def test_stt_raw_audio_contract_and_worker_thread(speech_api):
    client, services = speech_api
    audio = wav_bytes(0.5)
    response = await client.post("/api/stt", content=audio, headers={"Content-Type": "audio/wav"})
    assert response.status_code == 200
    assert response.json() == {"text": "Test question", "language": "en", "ms": 12}
    assert services["stt"].received == audio
    assert services["stt"].thread != threading.get_ident()


async def test_tts_wav_contract_and_worker_thread(speech_api):
    client, services = speech_api
    response = await client.post("/api/tts", json={"text": "  Hello campus.  "})
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "audio/wav"
    assert response.headers["Cache-Control"] == "no-store"
    with wave.open(io.BytesIO(response.content)) as wav:
        assert wav.getnframes() == 8000
    assert services["tts"].received == "Hello campus."
    assert services["tts"].thread != threading.get_ident()


async def test_stt_empty_and_over_limit_never_reach_model(speech_api, monkeypatch):
    client, services = speech_api
    assert (await client.post("/api/stt", content=b"")).status_code == 422
    monkeypatch.setattr(settings, "speech_max_audio_bytes", 4)

    async def chunks():
        yield b"abc"
        yield b"def"

    assert (await client.post("/api/stt", content=chunks())).status_code == 413
    assert services["stt"].received is None


@pytest.mark.parametrize("text", ["", "  ", "a" * (settings.speech_max_text_chars + 1)])
async def test_tts_rejects_empty_and_oversized_text(speech_api, text):
    client, services = speech_api
    assert (await client.post("/api/tts", json={"text": text})).status_code == 422
    assert services["tts"].received is None


@pytest.mark.parametrize("name,body", [("stt", {"content": b"audio"}), ("tts", {"json": {"text": "Hello"}})])
async def test_missing_model_is_visible_503(speech_api, name, body):
    client, services = speech_api
    services.pop(name)
    response = await client.post("/api/" + name, **body)
    assert response.status_code == 503
    assert "not available" in response.json()["detail"]


async def test_invalid_recording_is_actionable(speech_api):
    client, services = speech_api
    services["stt"].error = ValueError("The recording is too short")
    response = await client.post("/api/stt", content=b"audio")
    assert response.status_code == 422
    assert "too short" in response.json()["detail"]


@pytest.mark.parametrize("name,body", [("stt", {"content": b"audio"}), ("tts", {"json": {"text": "Hello"}})])
async def test_inference_failure_keeps_api_usable(speech_api, name, body):
    client, services = speech_api
    services[name].error = RuntimeError("private filesystem detail")
    response = await client.post("/api/" + name, **body)
    assert response.status_code == 503
    assert "private filesystem" not in response.text
    services[name].error = None
    assert (await client.post("/api/" + name, **body)).status_code == 200


async def test_inference_does_not_block_event_loop(speech_api):
    client, services = speech_api
    started, release = threading.Event(), threading.Event()

    def blocking(audio):
        started.set()
        assert release.wait(5), "event loop did not release inference worker"
        return {"text": "test", "language": "en", "ms": 1}

    services["stt"].transcribe = blocking
    request = asyncio.create_task(client.post("/api/stt", content=b"audio"))
    try:
        assert await asyncio.to_thread(started.wait, 2)
        assert (await client.post("/api/tts", json={"text": "Hello"})).status_code == 200
    finally:
        release.set()
    assert (await request).status_code == 200


@pytest.fixture
def decoder():
    pytest.importorskip("av")
    pytest.importorskip("numpy")
    stt = SpeechToText.__new__(SpeechToText)
    stt._lock = threading.Lock()
    stt.model = SimpleNamespace(transcribe=lambda *args, **kwargs: ([], SimpleNamespace(language="en")))
    return stt


def test_decoder_rejects_corrupt_audio(decoder):
    with pytest.raises(ValueError, match="Could not read"):
        decoder.transcribe(b"not audio")


def test_decoder_rejects_short_audio(decoder):
    with pytest.raises(ValueError, match="too short"):
        decoder.transcribe(wav_bytes(0.05))


def test_decoder_rejects_long_audio(decoder, monkeypatch):
    monkeypatch.setattr(settings, "speech_max_duration_s", 0.3)
    with pytest.raises(ValueError, match="under"):
        decoder.transcribe(wav_bytes(1))


def test_decoder_rejects_no_speech(decoder):
    with pytest.raises(ValueError, match="catch any speech"):
        decoder.transcribe(wav_bytes(0.5))
