"""Citation identity, prompt budgets, and resource cleanup acceptance checks."""
import importlib

import pytest

from backend.config import settings
from backend.llm.characters import character
from backend.llm.chat import cited_sources
from backend.llm.client import ChatMessage
from backend.llm.prompts import build_messages, excerpt
from backend.rag.store import Hit, sources_for
from backend.status import Registry


def hit(url, title="Fixture"):
    return Hit(text="Synthetic campus record", title=title, source_url=url, collection="campus", score=0.9)


def test_citation_numbers_survive_subset_and_deduplication():
    hits = [hit("https://example.org/a"), hit("https://example.org/b"), hit("https://example.org/a")]
    sources = cited_sources("Library details [2], campus details [3].", hits)
    assert [(s.url, s.citations) for s in sources] == [
        ("https://example.org/b", [2]), ("https://example.org/a", [3])]
    assert sources_for(hits)[0].citations == [1, 3]


def test_prompt_excerpt_finds_late_relevant_passage():
    text = "General college background. " * 100 + "Library visitors need a day pass. Library opens at 8 am."
    selected = excerpt(text, "When does the library open?", 300)
    assert "Library opens at 8 am" in selected
    assert len(selected) <= 300


def test_history_prompt_budget_keeps_latest_question(monkeypatch):
    monkeypatch.setattr(settings, "chat_history_chars", 90)
    history = [ChatMessage(role="user" if i % 2 == 0 else "assistant", content=f"Turn {i}: " + "x" * 50)
               for i in range(10)]
    messages = build_messages(character("guide"), "Current question", [], "", history, True)
    assert sum(len(m.content) for m in messages[1:-1]) <= 90
    assert messages[-2].content.startswith("Turn 9")
    assert messages[-1].content == "Current question"


class Resource:
    def __init__(self, fail_close=False):
        self.closed = 0
        self.fail_close = fail_close

    async def aclose(self):
        self.closed += 1
        if self.fail_close:
            raise RuntimeError("fixture close failure")


async def test_component_failure_isolated_and_cleanup_continues():
    registry = Registry()
    good, fails_close = Resource(), Resource(True)

    async def fail():
        raise RuntimeError("fixture missing model")

    async def load_good():
        return good

    async def load_fails_close():
        return fails_close

    registry.register("good", load_good)
    registry.register("missing", fail)
    registry.register("close_failure", load_fails_close)
    await registry.load_all()
    assert registry.get("good") is good and registry.get("missing") is None
    assert "fixture missing model" in registry.statuses["missing"].detail
    await registry.close_all()
    assert good.closed == 1 and fails_close.closed == 1
    assert registry.objects == {} and registry.get("good") is None


async def test_app_cleanup_runs_when_request_context_raises(monkeypatch):
    module = importlib.import_module("backend.app")
    registry, resource = Registry(), Resource()

    async def load():
        return resource

    registry.register("fixture", load)
    monkeypatch.setattr(module, "registry", registry)
    with pytest.raises(RuntimeError, match="fixture request failure"):
        async with module.lifespan(module.app):
            raise RuntimeError("fixture request failure")
    assert resource.closed == 1
