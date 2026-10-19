"""T1.2: locality schema and validator."""
import json
from pathlib import Path

from backend.rag import locality


def test_committed_file_valid_and_placeholders_flagged() -> None:
    ok, msgs = locality.validate()
    assert ok, msgs
    for e in locality.load():
        if e.name.startswith("PLACEHOLDER"):
            assert e.placeholder


def _write(tmp: Path, entries: list[dict]) -> Path:
    p = tmp / "loc.json"
    p.write_text(json.dumps(entries))
    return p


def test_rejects_future_date_and_bad_type(tmp_path: Path) -> None:
    base = {"id": "food-001", "type": "food", "name": "X", "last_checked": "2999-01-01"}
    assert not locality.validate(_write(tmp_path, [base]))[0]
    assert not locality.validate(_write(tmp_path, [{**base, "last_checked": "2026-01-01", "type": "bar"}]))[0]


def test_rejects_duplicate_ids(tmp_path: Path) -> None:
    e = {"id": "food-001", "type": "food", "name": "X", "last_checked": "2026-01-01"}
    assert not locality.validate(_write(tmp_path, [e, e]))[0]


async def test_unknown_veg_is_offered_as_not_confirmed(tmp_path):
    """A veg question with no confirmed veg place returns places whose veg options are unknown, labelled as such."""
    import json
    from backend.schedule.store import ScheduleStore
    from backend.tools import definitions  # noqa: F401
    from backend.tools.registry import ToolContext, run_tool
    loc = tmp_path / "loc.json"
    loc.write_text(json.dumps([
        {"id": "food-001", "type": "food", "name": "Fixture Cafe", "veg_options": None, "last_checked": "2026-10-19",
         "source_url": "https://example.org/cafe"},
        {"id": "food-002", "type": "food", "name": "Fixture Grill", "veg_options": False, "last_checked": "2026-10-19"}]))
    sched = ScheduleStore(tmp_path / "none.json", loc)
    r = await run_tool("get_local_tips", {"type": "food", "veg": True}, ToolContext(None, "chat", {"schedule": sched}))
    assert [i["name"] for i in r["items"]] == ["Fixture Cafe"] and "not confirmed" in r["note"]
    assert r["sources"][0]["url"] == "https://example.org/cafe"
    from backend.rag.locality import entry_text, load
    assert "veg options: not confirmed" in entry_text(load(loc)[0])
