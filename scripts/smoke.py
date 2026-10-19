"""Core local-model acceptance check. Does not claim speech or gesture readiness."""
import asyncio
import json
import time

import httpx

from backend.app import app


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


async def main():
    start = time.perf_counter()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=180) as client:
            health = (await client.get("/api/health")).json()
            for name in ("llm", "rag", "memory"):
                assert health["components"][name]["ok"], health
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
    print(f"Core smoke PASS in {time.perf_counter() - start:.1f}s. Speech, gestures and physical offline demo are not covered.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
