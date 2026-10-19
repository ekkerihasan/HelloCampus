"""Core local-model acceptance check. Does not claim speech or gesture readiness."""
import asyncio
import argparse
import io
import json
import time
import wave
import socket
import ipaddress
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import httpx

from backend.app import app
from backend.config import settings
from backend.hiring.service import student_data
from backend.status import registry


def parse(response):
    response.raise_for_status()
    events = []
    for frame in response.text.strip().split("\n\n"):
        lines = frame.splitlines()
        events.append((lines[0].removeprefix("event: "), json.loads(lines[1].removeprefix("data: "))))
    errors = [data for event, data in events if event == "error"]
    assert not errors, errors
    assert events[-1][0] == "done", events
    return events


async def main(check_speech: bool = False, full: bool = False, gesture_samples: Path | None = None):
    start = time.perf_counter()
    if full:
        assert student_data(), "Full smoke needs currently opted-in student records"
        assert gesture_samples is not None and gesture_samples.is_dir(), "Provide --gesture-samples with real labeled frame folders"
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=180) as client:
            health = (await client.get("/api/health")).json()
            for name in ("llm", "rag", "memory"):
                assert health["components"][name]["ok"], health
            if check_speech or full:
                for name in ("stt", "tts"):
                    assert health["components"][name]["ok"], health
            if full:
                assert health["components"].get("gesture", {}).get("ok"), "Full smoke needs real trained gesture weights"
            print("PASS: local components", flush=True)
            for character in ("guide", "analyst"):
                evs = parse(await client.post("/api/chat", json={"message": "How can I contact AITM?", "character": character}))
                sources = next(data for event, data in evs if event == "sources")
                assert not sources["refused"] and sources["sources"], sources
                assert all(s["url"].startswith("https://aitm.edu.in/") for s in sources["sources"])
                assert "token" in [event for event, _ in evs]
                print(f"PASS: {character} generates with AITM sources", flush=True)
            evs = parse(await client.post("/api/chat", json={"message": "Purple quantum banana spaceship timetable?"}))
            assert next(data for event, data in evs if event == "sources")["refused"]
            print("PASS: unrelated question refused", flush=True)
            v = (await client.post("/api/visitor", json={"name": "Smoke check", "purpose": "Hiring"})).json()
            evs = parse(await client.post("/api/chat", json={"message": "I prefer vegetarian lunch near campus.", "visitor_id": v["id"]}))
            assert ("memory", {"status": "saved"}) in evs, evs
            resumed = (await client.get("/api/visitor/resume/" + v["code"])).json()
            assert resumed["purpose"] == "Hiring" and resumed["facts"].get("preferences"), resumed
            assert "veget" in json.dumps(resumed["facts"]).lower(), resumed
            print("PASS: local fact extraction and cross-session resume", flush=True)
            shortlist = await client.get("/api/hiring/shortlist/" + v["id"])
            assert shortlist.status_code == 200 and shortlist.json() == []
            print("PASS: honest empty shortlist", flush=True)
            if full:
                role = await client.post("/api/hiring/role", json={"visitor_id": v["id"],
                    "description": "Software development intern, with documented project experience"})
                role.raise_for_status()
                matches = await client.post("/api/hiring/match", json={"visitor_id": v["id"]})
                matches.raise_for_status()
                assert matches.json(), "Full smoke requires a real evidence-backed hiring match"
                person = matches.json()[0]
                added = await client.post("/api/hiring/shortlist", json={"visitor_id": v["id"], "entity_id": person["entity_id"]})
                added.raise_for_status()
                exported = await client.get("/api/hiring/export/" + v["id"])
                exported.raise_for_status()
                assert person["name"] in exported.text
                detector = registry.get("gesture")
                for label in settings.gesture_classes:
                    frames = sorted((gesture_samples / label).glob("*.jpg"))
                    assert frames, f"Missing real sample frames for {label}"
                    detections = await asyncio.to_thread(detector.predict, frames[0].read_bytes())
                    if label == "no_gesture":
                        assert all(d.label == "no_gesture" for d in detections), detections
                    else:
                        assert detections and detections[0].label == label, f"Real sample did not detect {label}: {detections}"
                print("PASS: real gesture samples and populated hiring path", flush=True)
            if check_speech or full:
                seed = await client.post("/api/tts", json={"text": "Hello campus. Where is the library?"})
                seed.raise_for_status()
                roundtrip_start = time.perf_counter()
                transcript = await client.post("/api/stt", content=seed.content, headers={"Content-Type": "audio/wav"})
                transcript.raise_for_status()
                assert "library" in transcript.json()["text"].lower(), transcript.text
                audio = await client.post("/api/tts", json={"text": transcript.json()["text"]})
                audio.raise_for_status()
                with wave.open(io.BytesIO(audio.content)) as wav:
                    assert wav.getnframes() > 0
                elapsed = time.perf_counter() - roundtrip_start
                print(f"PASS: speech endpoints roundtrip {elapsed:.2f}s; six-second target {'PASS' if elapsed < 6 else 'UNMET'}", flush=True)
                if full:
                    assert elapsed < 6, "Full smoke requires the six-second speech target"
            gesture = await client.get("/api/gesture/config")
            assert gesture.status_code == 200 and gesture.json()["hold_ms"] > 0
            print("PASS: gesture availability/config is explicit", flush=True)
    scope = "Full endpoint" if full else f"Core{' + speech' if check_speech else ''}"
    print(f"{scope} smoke PASS in {time.perf_counter() - start:.1f}s. "
          "Physical phone, venue repetition and Wi-Fi-off demo checks are separate.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speech", action="store_true", help="Also verify real STT/TTS endpoints")
    parser.add_argument("--full", action="store_true", help="Require trained weights and speech timing readiness")
    parser.add_argument("--offline", action="store_true", help="Block non-loopback Python socket connections")
    parser.add_argument("--gesture-samples", type=Path, help="Real venue JPEGs under one folder per gesture class")
    options = parser.parse_args()
    if options.full and options.gesture_samples is None:
        parser.error("--full requires --gesture-samples with real labeled venue JPEGs")
    connect = socket.socket.connect
    def loopback_connect(sock, address):
        if isinstance(address, tuple):
            host = address[0]
            try:
                allowed = host == "localhost" or ipaddress.ip_address(host).is_loopback
            except ValueError:
                allowed = False
            if not allowed:
                raise RuntimeError("Offline smoke blocked a non-loopback Python network connection")
        return connect(sock, address)
    with ExitStack() as stack:
        if options.offline:
            stack.enter_context(patch("socket.socket.connect", loopback_connect))
            print("Python network guard: only loopback connections allowed", flush=True)
        asyncio.run(main(options.speech, options.full, options.gesture_samples))
