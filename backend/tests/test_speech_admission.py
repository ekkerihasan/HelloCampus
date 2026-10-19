"""Admission and cancellation checks with controlled workers, without model weights."""
import asyncio
import threading
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException, Request
import httpx
import pytest

from backend.routes import speech


def consumed_request(disconnected: bool = False):
    messages = asyncio.Queue()
    if disconnected:
        messages.put_nowait({"type": "http.disconnect"})
    request = Request({"type": "http", "method": "POST", "path": "/api/tts", "headers": []},
                      receive=messages.get)
    return request, messages


@pytest.fixture
def workers(monkeypatch):
    controlled = {name: speech.SpeechWorker(name) for name in ("stt", "tts")}
    monkeypatch.setattr(speech, "_workers", controlled)
    yield controlled
    for worker in controlled.values():
        worker._executor.shutdown(wait=True, cancel_futures=True)


@pytest.mark.parametrize("name,body", [("stt", {"content": b"audio"}), ("tts", {"json": {"text": "Hello"}})])
async def test_busy_model_rejects_excess_with_visible_503(workers, monkeypatch, name, body):
    started, release = threading.Event(), threading.Event()
    calls = []

    def blocked(value):
        calls.append(value)
        started.set()
        assert release.wait(3)
        return {"text": "hello", "language": "en", "ms": 1} if name == "stt" else b"wav"

    models = {"stt": SimpleNamespace(transcribe=blocked), "tts": SimpleNamespace(synthesize=blocked)}
    from backend.status import registry
    monkeypatch.setattr(registry, "get", models.get)
    app = FastAPI()
    app.include_router(speech.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        first = asyncio.create_task(client.post(f"/api/{name}", **body))
        try:
            assert await asyncio.to_thread(started.wait, 2)
            rejected = await client.post(f"/api/{name}", **body)
            assert rejected.status_code == 503
            assert "busy finishing a previous request" in rejected.json()["detail"]
            assert len(calls) == 1
        finally:
            release.set()
        assert (await first).status_code == 200
        assert (await client.post(f"/api/{name}", **body)).status_code == 200


@pytest.mark.parametrize("disconnect", [True, False])
async def test_cancellation_or_disconnect_keeps_running_worker_slot(workers, disconnect):
    started, release = threading.Event(), threading.Event()

    def blocked():
        started.set()
        assert release.wait(3)
        return "finished"

    request, messages = consumed_request()
    job = asyncio.create_task(speech._infer(request, "tts", blocked))
    try:
        assert await asyncio.to_thread(started.wait, 2)
        if disconnect:
            messages.put_nowait({"type": "http.disconnect"})
            with pytest.raises(HTTPException) as stopped:
                await job
            assert stopped.value.status_code == 503
        else:
            job.cancel()
            with pytest.raises(asyncio.CancelledError):
                await job
        new_request, _ = consumed_request()
        with pytest.raises(HTTPException) as rejected:
            await speech._infer(new_request, "tts", lambda: "must not run")
        assert rejected.value.status_code == 503
        # Another model has an independent slot even while TTS finishes.
        other_request, _ = consumed_request()
        assert await speech._infer(other_request, "stt", lambda: "independent") == "independent"
    finally:
        release.set()
    await asyncio.wrap_future(workers["tts"]._executor.submit(lambda: None))
    request, _ = consumed_request()
    assert await speech._infer(request, "tts", lambda: "next") == "next"


async def test_disconnected_request_never_enters_inference(workers):
    request, _ = consumed_request(disconnected=True)
    calls = []
    with pytest.raises(HTTPException) as rejected:
        await speech._infer(request, "stt", lambda: calls.append("unexpected"))
    assert rejected.value.status_code == 503
    assert calls == []
    request, _ = consumed_request()
    assert await speech._infer(request, "stt", lambda: "available") == "available"


@pytest.mark.parametrize("disconnect", [True, False])
async def test_disconnect_or_cancellation_skips_not_started_job(workers, disconnect):
    occupied, release = threading.Event(), threading.Event()

    def occupy_executor():
        occupied.set()
        assert release.wait(3)

    # Delay thread dispatch to exercise a cancellation before model invocation.
    blocker = workers["tts"]._executor.submit(occupy_executor)
    assert await asyncio.to_thread(occupied.wait, 2)
    calls = []
    request, messages = consumed_request()
    job = asyncio.create_task(speech._infer(request, "tts", lambda: calls.append("unexpected")))
    try:
        # Wait until admission occurred, without relying on a fixed sleep.
        for _ in range(100):
            if workers["tts"]._slot.locked():
                break
            await asyncio.sleep(0)
        assert workers["tts"]._slot.locked()
        if disconnect:
            messages.put_nowait({"type": "http.disconnect"})
            with pytest.raises(HTTPException) as rejected:
                await job
            assert rejected.value.status_code == 503
        else:
            job.cancel()
            with pytest.raises(asyncio.CancelledError):
                await job
    finally:
        release.set()
    await asyncio.wrap_future(blocker)
    await asyncio.wrap_future(workers["tts"]._executor.submit(lambda: None))
    assert calls == []
    assert not workers["tts"]._slot.locked()


def test_admission_workers_are_reusable_across_event_loops(workers):
    async def one_loop(value):
        request, _ = consumed_request()
        return await speech._infer(request, "tts", lambda: value)

    assert asyncio.run(one_loop("first")) == "first"
    assert asyncio.run(one_loop("second")) == "second"
