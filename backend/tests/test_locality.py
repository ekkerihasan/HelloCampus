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
