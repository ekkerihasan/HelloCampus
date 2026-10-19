"""Deterministic endpoint acceptance checks. Synthetic fixtures never enter data/."""
import json
from pathlib import Path

import httpx
import pytest

from backend.app import app
from backend.config import settings
from backend.llm.prompts import is_smalltalk
from backend.memory.store import MemoryStore, visitor_block
from backend.rag.store import Hit
from backend.status import registry


class FakeLLM:
    def __init__(self):
        self.temperatures = []
        self.messages = []
        self.fail_memory = False

    async def stream_chat(self, messages, temperature):
        self.messages = messages
        self.temperatures.append(temperature)
        for token in ("The library ", "opens at 8 am", " [1]."):
            yield token

    async def chat_json(self, messages):
        if self.fail_memory:
            raise RuntimeError("fixture model unavailable")
        return {"preferences": ["vegetarian"], "interests": [], "plans": [],
                "summary": "The visitor prefers vegetarian food."}


class FakeRAG:
    def __init__(self):
        self.hits = [Hit(text="Synthetic library hours: 8 am", title="Fixture library",
            source_url="https://example.org/library", collection="campus", score=0.9)]

    async def retrieve(self, question, collections):
        return self.hits


@pytest.fixture
async def api(tmp_path: Path, monkeypatch):
    mem, llm, rag = MemoryStore(tmp_path / "memory.db"), FakeLLM(), FakeRAG()
    services = {"memory": mem, "llm": llm, "rag": rag}
    monkeypatch.setattr(registry, "get", services.get)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, services
    mem.close()


def events(response):
    assert response.status_code == 200
    return [(line.splitlines()[0].removeprefix("event: "),
             json.loads(line.splitlines()[1].removeprefix("data: ")))
            for line in response.text.strip().split("\n\n")]


@pytest.mark.parametrize("character,temp", [("guide", 0.8), ("analyst", 0.2)])
async def test_chat_streams_then_sources(api, character, temp):
    client, services = api
    evs = events(await client.post("/api/chat", json={"message": "When does the library open?",
                                                    "character": character}))
    names = [e[0] for e in evs]
    assert names == ["meta", "token", "token", "token", "sources", "done"]
    assert evs[-2][1]["sources"][0]["url"] == "https://example.org/library"
    assert services["llm"].temperatures == [temp]


async def test_refusal_never_calls_generation(api):
    client, services = api
    services["rag"].hits = []
    evs = events(await client.post("/api/chat", json={"message": "When does the library open?"}))
    assert evs[1][1]["t"].startswith("I don't have that yet")
    assert evs[2][1] == {"sources": [], "refused": True}
    assert services["llm"].temperatures == []


async def test_visitor_resume_remembers_and_injects_facts(api):
    client, services = api
    v = (await client.post("/api/visitor", json={"name": "Fixture Visitor", "purpose": "Hiring"})).json()
    assert len(v["code"]) == settings.resume_code_length
    evs = events(await client.post("/api/chat", json={"message": "I prefer vegetarian lunch near campus",
                                                    "visitor_id": v["id"]}))
    assert ("memory", {"status": "saved"}) in evs
    resumed = (await client.get("/api/visitor/resume/" + v["code"].lower())).json()
    assert resumed["purpose"] == "Hiring"
    assert resumed["facts"]["preferences"] == ["vegetarian"]
    await client.post("/api/chat", json={"message": "hello", "visitor_id": resumed["id"]})
    assert "vegetarian" in services["llm"].messages[0].content


async def test_memory_failure_preserves_answer(api):
    client, services = api
    services["llm"].fail_memory = True
    v = (await client.post("/api/visitor", json={"name": "Fixture Visitor"})).json()
    evs = events(await client.post("/api/chat", json={"message": "library hours", "visitor_id": v["id"]}))
    assert evs[-2][1]["status"] == "failed" and evs[-1][0] == "done"
    assert len(services["memory"].history(v["id"])) == 2


async def test_validation_and_missing_services(api):
    client, services = api
    assert (await client.post("/api/visitor", json={"name": "  "})).status_code == 422
    assert (await client.post("/api/chat", json={"message": "  "})).status_code == 422
    assert (await client.get("/api/visitor/resume/ZZZZ")).status_code == 404
    evs = events(await client.post("/api/chat", json={"message": "hello", "visitor_id": "missing"}))
    assert evs[0][0] == "error"
    services.pop("llm")
    assert (await client.post("/api/chat", json={"message": "hello"})).status_code == 503


def test_history_bounded_and_memory_survives_restart(tmp_path):
    path = tmp_path / "memory.db"
    mem = MemoryStore(path)
    v = mem.create("Fixture Visitor", "Hiring")
    mem.update(v.id, facts={"preferences": ["vegetarian"]})
    for i in range(30):
        mem.add_turn(v.id, "user", str(i))
    mem.close()
    reopened = MemoryStore(path)
    assert len(reopened.history(v.id)) == settings.memory_max_turns
    assert reopened.history(v.id)[-1].content == "29"
    assert "vegetarian" in visitor_block(reopened.by_code(v.code))
    reopened.close()


def test_greeting_cannot_bypass_grounding():
    assert is_smalltalk("Hello!")
    assert not is_smalltalk("Hi fees?")
    assert not is_smalltalk("Hello, when does the library open?")
