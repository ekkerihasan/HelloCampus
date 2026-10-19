"""Local ranking covers the full eligible set and requires no provider calls."""
import json
from datetime import date

import pytest

from backend.config import settings
from backend.rag.local_recommend import vegetarian_request
from backend.schedule.store import ScheduleStore
from backend.tools import definitions  # noqa: F401
from backend.tools.registry import ToolContext, run_tool


@pytest.fixture
def places(tmp_path):
    stores = []

    def build(rows):
        path = tmp_path / "locality.json"
        path.write_text(json.dumps([
            {"id": f"food-{i:03}", "type": "food", "name": f"Cafe {i:02}",
             "last_checked": date.today().isoformat(), "source_url": f"https://example.org/{i}",
             **row} for i, row in enumerate(rows, 1)
        ]), encoding="utf-8")
        store = ScheduleStore(tmp_path / "missing.json", path)
        stores.append(store)
        return store

    yield build
    for store in stores:
        store.close()


async def tips(store, args=None, message="", mode="chat"):
    class UnavailableRag:
        async def retrieve(self, *args, **kwargs):
            raise AssertionError("curated tips must not require embeddings")

    return await run_tool("get_local_tips", {"type": "food", **(args or {})},
                          ToolContext(None, mode, {"schedule": store, "rag": UnavailableRag()}, message))


async def test_matching_ninth_place_is_ranked_before_limit(places):
    result = await tips(places([{} for _ in range(8)] + [{"name": "Zebra Kitchen", "cuisine": "Konkani"}]),
                        {"query": "Konkani lunch"})
    assert result["items"][0]["name"] == "Zebra Kitchen"
    assert result["sources"][0]["url"] == "https://example.org/9"
    assert len(result["items"]) == settings.rag_top_k_chat


async def test_visitor_words_preserve_diet(places):
    result = await tips(places([{"veg_options": False}, {"veg_options": True}]),
                        {"query": "lunch", "veg": False}, "Vegetarian lunch please")
    assert [i["id"] for i in result["items"]] == ["food-002"]


async def test_unknown_veg_fallback_labeled_and_placeholders_hidden(places):
    result = await tips(places([{"veg_options": False}, {"veg_options": None},
                               {"veg_options": True, "placeholder": True}]), {"veg": True})
    assert [i["id"] for i in result["items"]] == ["food-002"]
    assert "not confirmed" in result["note"]
    assert result["items"][0]["price_range"] == ""


async def test_no_dietary_match_refuses(places):
    result = await tips(places([{"veg_options": False}]), {"veg": True})
    assert result["refusal"] and result["sources"] == []


async def test_confirmed_veg_excludes_unknowns_and_voice_limit(places, monkeypatch):
    monkeypatch.setattr(settings, "rag_top_k_voice", 1)
    result = await tips(places([{"veg_options": None}, {"veg_options": True}, {"veg_options": True}]),
                        {"veg": True}, mode="voice")
    assert len(result["items"]) == 1 and result["items"][0]["veg_options"] is True
    assert "not confirmed" not in result["note"]


async def test_original_query_ranks_without_model_query_or_embeddings(places):
    result = await tips(places([{"name": "Alpha Cafe"}, {"name": "Zebra Kitchen"}]), message="Zebra Kitchen")
    assert result["items"][0]["name"] == "Zebra Kitchen"
    assert "open now" in result["note"]


@pytest.mark.parametrize("text", ["non-veg lunch", "non vegetarian lunch", "not vegetarian", "no veg"])
def test_nonveg_does_not_imply_vegetarian(text):
    assert not vegetarian_request(text)
