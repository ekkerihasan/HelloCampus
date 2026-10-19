"""T1.6/T1.7 endpoint acceptance: tool call, streamed answer, sources from tool results only, refusal without
generation, character temperatures, memory with language and resume. Controlled doubles, no network."""
import json
from pathlib import Path

import httpx
import pytest

from backend.app import app
from backend.llm.client import ChatMessage, ToolCall
from backend.llm.prompts import REFUSAL, is_smalltalk
from backend.memory.store import MemoryStore, visitor_block
from backend.rag.store import VectorStore
from backend.schedule.store import ScheduleStore
from backend.status import registry
from backend.tests.fixtures import FIXTURE_RECORDS


class FakeLLM:
    active = "fake"

    def __init__(self):
        self.temperatures: list[float] = []
        self.next_tool = ("search_campus", {"query": "When is the library open on Saturday?"})
        self.fail_memory = False
        self.complete_calls = 0
        self.last_messages: list[ChatMessage] = []

    async def complete(self, messages, temperature, tools=None, tool_choice="auto", **kw):
        self.complete_calls += 1
        name, args = self.next_tool
        return ChatMessage(role="assistant", tool_calls=[ToolCall(id="c1", name=name, arguments=args)])

    async def stream_chat(self, messages, temperature):
        self.last_messages = messages
        self.temperatures.append(temperature)
        for token in ("The library ", "opens at 9 am on Saturdays", " [1]."):
            yield token

    async def chat_json(self, messages, temperature=None):
        if self.fail_memory:
            raise RuntimeError("fixture model unavailable")
        return {"preferences": ["vegetarian"], "interests": [], "plans": [], "language": "hi",
                "summary": "The visitor prefers vegetarian food."}


@pytest.fixture
async def api(tmp_path: Path, monkeypatch, embedder):
    store = VectorStore(embedder, tmp_path / "chroma", tmp_path / "cache.sqlite3")
    for col, recs in FIXTURE_RECORDS.items():
        await store.ingest(col, recs, whole=col != "campus")
    sched = ScheduleStore(tmp_path / "missing.json", tmp_path / "missing-loc.json")
    mem, llm = MemoryStore(tmp_path / "memory.db"), FakeLLM()
    services = {"memory": mem, "llm": llm, "rag": store, "schedule": sched}
    monkeypatch.setattr(registry, "get", services.get)
    monkeypatch.setattr(registry, "loaders", {k: None for k in services})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, services
    mem.close()
    await store.aclose()


def events(response):
    assert response.status_code == 200
    return [(chunk.splitlines()[0].removeprefix("event: "), json.loads(chunk.splitlines()[1].removeprefix("data: ")))
            for chunk in response.text.strip().split("\n\n")]


async def test_tool_then_stream_then_sources(api):
    client, services = api
    evs = events(await client.post("/api/chat", json={"message": "When is the library open on Saturday?",
                                                      "character": "analyst"}))
    names = [e for e, _ in evs]
    assert names[0] == "meta" and "tool" in names and names[-1] == "done"
    assert names.index("tool") < names.index("token") < names.index("sources")
    sources = next(d for e, d in evs if e == "sources")
    assert sources["refused"] is False
    assert [s["url"] for s in sources["sources"]] == ["https://example.org/fixture/library"]
    assert services["llm"].temperatures == [0.2]
    tool_msg = next(m for m in services["llm"].last_messages if m.role == "tool")
    assert "Fixture Institute library hours" in tool_msg.content


async def test_refusal_skips_generation(api):
    client, services = api
    services["llm"].next_tool = ("search_campus", {"query": "purple elephant quantum banana"})
    evs = events(await client.post("/api/chat", json={"message": "purple elephant quantum banana"}))
    assert next(d for e, d in evs if e == "token")["t"] == REFUSAL
    assert next(d for e, d in evs if e == "sources") == {"sources": [], "refused": True}
    assert services["llm"].temperatures == []  # nothing generated, so nothing can be invented


async def test_schedule_never_guessed(api):
    client, services = api
    services["llm"].next_tool = ("get_schedule", {"date": "2026-10-20"})
    evs = events(await client.post("/api/chat", json={"message": "When is the keynote tomorrow?"}))
    assert next(d for e, d in evs if e == "sources")["refused"] is True


async def test_smalltalk_uses_no_tools_and_guide_temperature(api):
    client, services = api
    events(await client.post("/api/chat", json={"message": "hello!", "character": "guide"}))
    assert services["llm"].complete_calls == 0 and services["llm"].temperatures == [0.8]


async def test_memory_language_and_resume(api):
    client, services = api
    v = (await client.post("/api/visitor", json={"name": "Asha", "purpose": "Session or talk"})).json()
    evs = events(await client.post("/api/chat", json={"message": "When is the library open on Saturday?",
                                                      "visitor_id": v["id"]}))
    assert ("memory", {"status": "saved"}) in evs
    resumed = (await client.get(f"/api/visitor/resume/{v['code'].lower()}")).json()
    assert resumed["purpose"] == "Session or talk" and resumed["language"] == "hi"
    assert resumed["facts"]["preferences"] == ["vegetarian"]
    block = visitor_block(services["memory"].get(v["id"]))
    assert "Speaks: hi" in block and "vegetarian" in block
    assert len(services["memory"].history(v["id"])) == 2


async def test_memory_failure_is_visible_and_nonfatal(api):
    client, services = api
    services["llm"].fail_memory = True
    v = (await client.post("/api/visitor", json={"name": "Ravi"})).json()
    evs = events(await client.post("/api/chat", json={"message": "When is the library open on Saturday?",
                                                      "visitor_id": v["id"]}))
    assert any(e == "memory" and d["status"] == "failed" for e, d in evs)
    assert evs[-1][0] == "done"


async def test_turn_retention_limit(tmp_path: Path):
    mem = MemoryStore(tmp_path / "m.db")
    v = mem.create("Test")
    for i in range(14):
        mem.add_turn(v.id, "user", f"m{i}")
    assert [m.content for m in mem.history(v.id)][0] == "m4" and len(mem.history(v.id)) == 10
    mem.close()


async def test_unknown_visitor_and_blank_message(api):
    client, _ = api
    evs = events(await client.post("/api/chat", json={"message": "hi", "visitor_id": "nope"}))
    assert evs[0][0] == "error"
    assert (await client.post("/api/chat", json={"message": "   "})).status_code == 422


def test_smalltalk_detection():
    assert is_smalltalk("Hi!") and is_smalltalk("namaste")
    assert not is_smalltalk("hi, when does the library open?")


def test_chips_narrow_to_cited_numbers_only():
    from backend.llm.chat import merge_sources
    search = {"sources": [{"title": "A", "url": "https://example.org/a", "citations": [1]},
                          {"title": "B", "url": "https://example.org/b", "citations": [2]}]}
    tips = {"sources": [{"title": "Cafe", "url": "curated", "citations": []}]}
    assert [s["url"] for s in merge_sources([("search_campus", search)], "Fact [2].")] == ["https://example.org/b"]
    assert merge_sources([("search_campus", search)], "No markers.") == []  # nothing cited: no chips (M-010)
    assert merge_sources([("get_local_tips", tips)], "Try it [1].")[0]["title"] == "Cafe"


async def test_language_ignores_short_fragments_and_unsupported_languages(tmp_path: Path):
    from backend.memory.extract import extract_and_save
    mem = MemoryStore(tmp_path / "m.db")
    v = mem.create("Wasih")

    class Lang(FakeLLM):
        def __init__(self, code):
            super().__init__()
            self.code = code

        async def chat_json(self, messages, temperature=None):
            return {"preferences": [], "interests": [], "plans": [], "language": self.code, "summary": "s"}

    v = await extract_and_save(Lang("es"), mem, v, "el nombre", "")  # misheard fragment
    assert v.language == ""
    v = await extract_and_save(Lang("es"), mem, v, "where is the main library on campus", "")  # unsupported
    assert v.language == ""
    v = await extract_and_save(Lang("hi"), mem, v, "लाइब्रेरी कब खुलती है आज", "")
    assert v.language == "hi"
    v = await extract_and_save(Lang("en"), mem, v, "ok", "")  # too short to switch back
    assert v.language == "hi"
    mem.close()


async def test_greeting_with_profile_tool_is_not_refused(api):
    """M-009: 'Hi! I just arrived on campus.' made the model call get_visitor_profile, which became a refusal."""
    client, services = api
    services["llm"].next_tool = ("get_visitor_profile", {})
    evs = events(await client.post("/api/chat", json={"message": "Hi! I just arrived on campus."}))
    assert next(d for e, d in evs if e == "sources") == {"sources": [], "refused": False}
    assert services["llm"].temperatures == [0.8]
    assert any("No campus data was looked up" in m.content for m in services["llm"].last_messages if m.role == "system")


async def test_empty_stream_retries_then_refuses(api):
    """M-010: a stream with zero tokens must not show an empty answer with chips."""
    client, services = api
    llm = services["llm"]

    async def empty(messages, temperature):
        llm.temperatures.append(temperature)
        return
        yield  # noqa: unreachable, makes this an async generator

    async def complete(messages, temperature, tools=None, tool_choice="auto", **kw):
        llm.complete_calls += 1
        if tools:
            return ChatMessage(role="assistant", tool_calls=[ToolCall(id="c1", name="search_campus",
                                                                      arguments={"query": "library Saturday"})])
        return ChatMessage(role="assistant", content="")

    llm.stream_chat, llm.complete = empty, complete
    evs = events(await client.post("/api/chat", json={"message": "When is the library open on Saturday?"}))
    assert next(d for e, d in evs if e == "token")["t"] == REFUSAL
    assert next(d for e, d in evs if e == "sources") == {"sources": [], "refused": True}
    assert llm.complete_calls == 2  # tool choice plus one non-streamed retry


def test_direct_search_only_for_plain_campus_questions():
    from backend.llm.chat import direct_search
    assert direct_search("What is the placement rate at AITM?")
    assert direct_search("Tell me about the CSE department")
    for msg in ("When does the library open?", "Where can I get lunch?", "I'm hiring a frontend intern",
                "hello, I'm here for the hackathon", "Remember that I am vegetarian"):
        assert not direct_search(msg), msg


async def test_plain_question_skips_tool_choice_call(api):
    client, services = api
    events(await client.post("/api/chat", json={"message": "Tell me about the Fixture Institute robotics club"}))
    assert services["llm"].complete_calls == 0 and services["llm"].temperatures == [0.8]
    # Gemini 3 rejects history with a function call it did not make (no thought_signature): results go in as context.
    assert not any(m.tool_calls for m in services["llm"].last_messages)
    assert any("search_campus result" in m.content for m in services["llm"].last_messages if m.role == "system")


async def test_greeting_with_empty_schedule_still_greets(api):
    """M-009 reopened: a greeting whose lookup found nothing greets and says it is not available, no canned refusal."""
    client, services = api
    services["llm"].next_tool = ("get_schedule", {})
    evs = events(await client.post("/api/chat", json={"message": "hello, I'm here for the hackathon"}))
    assert next(d for e, d in evs if e == "sources") == {"sources": [], "refused": False}
    assert any("greeted you" in m.content for m in services["llm"].last_messages if m.role == "system")


def test_grouped_citations_are_parsed():
    """M-012: grouped citations must keep their chips."""
    from backend.llm.chat import cited_numbers
    assert cited_numbers("Fact [1, 2].") == {1, 2}
    assert cited_numbers("Fact [1,2].") == {1, 2}
    assert cited_numbers("Fact [1][2].") == {1, 2}
    assert cited_numbers("Facts [1-3] and [5].") == {1, 2, 3, 5}
    assert cited_numbers("Range [2–4].") == {2, 3, 4}
    assert cited_numbers("No citations, just [a note].") == set()
