"""Prompt budgets, tool schema shape, and resource cleanup acceptance checks."""
import importlib

import pytest

from backend.config import settings
from backend.llm.client import ChatMessage
from backend.llm.prompts import recent_history
from backend.status import Registry
from backend.tools import definitions  # noqa: F401, registers the tools
from backend.tools.registry import TOOLS, chat_tools, live_declarations


def test_history_prompt_budget_keeps_latest_turn(monkeypatch):
    monkeypatch.setattr(settings, "chat_history_chars", 90)
    history = [ChatMessage(role="user" if i % 2 == 0 else "assistant", content=f"Turn {i}: " + "x" * 50)
               for i in range(10)]
    recent = recent_history(history)
    assert sum(len(m.content) for m in recent) <= 90
    assert recent[-1].content.startswith("Turn 9")


def test_tool_schemas_are_provider_safe():
    """Both providers reject JSON-schema extras such as anyOf, title and default."""
    text = str(chat_tools()) + str(live_declarations())
    assert "anyOf" not in text and "'title'" not in text and "'default'" not in text and "$ref" not in text
    assert {t["function"]["name"] for t in chat_tools()} == {n for n, t in TOOLS.items() if t.chat}
    assert "look" not in {t["function"]["name"] for t in chat_tools()}  # needs the camera


def test_grounding_tools_block_on_live():
    """M-004: grounding tools must finish before the host speaks; writes may run in the background."""
    behavior = {d["name"]: d["behavior"] for d in live_declarations()}
    for name in ("search_campus", "get_local_tips", "get_schedule", "look", "hiring_match", "get_visitor_profile"):
        assert behavior[name] == "BLOCKING"
    for name in ("remember", "shortlist_add", "shortlist_remove"):
        assert behavior[name] == "NON_BLOCKING"


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
