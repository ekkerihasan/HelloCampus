import asyncio
import json
import sys
from unittest.mock import patch

import pytest

from backend.quiz.bank import load_bank, read_records, validate_bank
from backend.quiz.generate import generate_bank
from backend.quiz.generate import main


def fixture(tmp_path):
    record = {"collection": "campus", "source_url": "https://aitm.edu.in/about/",
              "text": "AITM was established in 1980. Its campus is in Bhatkal."}
    (tmp_path / "campus.jsonl").write_text(json.dumps(record), encoding="utf-8")
    item = {"id": "year", "question": "When was AITM established?",
            "options": ["1980", "1995", "2010", "1993"], "answer_index": 0,
            "source_url": record["source_url"], "evidence": "AITM was established in 1980."}
    return record, item


def test_load_revalidates_and_deduplicates(tmp_path):
    _, item = fixture(tmp_path)
    path = tmp_path / "quiz.jsonl"
    path.write_text(json.dumps(item) + "\n" + json.dumps(item), encoding="utf-8")
    assert len(load_bank(path, tmp_path)) == 1
    (tmp_path / "campus.jsonl").write_text("", encoding="utf-8")
    assert load_bank(path, tmp_path) == []


def test_rejects_invalid_items(tmp_path):
    _, item = fixture(tmp_path)
    records = read_records(tmp_path)
    variants = [
        {"evidence": "AITM was established in 1995."},
        {"source_url": "https://aitm.edu.in/unknown/"},
        {"answer_index": True}, {"answer_index": 4},
        {"options": ["1980", "1980", "2010", "1993"]},
        {"options": ["1980", "", "2010", "1993"]},
        {"evidence": "1980"}, {"answer_index": 1},
        {"evidence": "             "}, {"evidence": 1980},
        {"options": "1980"}, {"options": [1980, "1995", "2010", "1993"]},
    ]
    for variant in variants:
        assert validate_bank([{**item, **variant}], records) == []


def test_evidence_must_be_in_same_record(tmp_path):
    record, item = fixture(tmp_path)
    records = [record, {**record, "source_url": "https://aitm.edu.in/contact/",
                        "text": "A different record."}]
    assert validate_bank([{**item, "source_url": records[1]["source_url"]}], records) == []


def test_only_public_campus_corpus(tmp_path):
    record, _ = fixture(tmp_path)
    variants = [{**record, "collection": "students"}, {**record, "private": True},
                {**record, "extra": {"placeholder": True}},
                {**record, "source_url": "https://example.org/"}]
    (tmp_path / "other.jsonl").write_text("\n".join(map(json.dumps, variants)), encoding="utf-8")
    assert len(read_records(tmp_path)) == 1


def test_injected_generator(tmp_path):
    _, item = fixture(tmp_path)

    async def adapter(records):
        assert len(records) == 1
        return [item]

    assert len(asyncio.run(generate_bank(tmp_path, adapter))) == 1


def test_normalized_duplicate_question(tmp_path):
    record, item = fixture(tmp_path)
    duplicate = {**item, "id": "different", "question": "  WHEN was AITM established?  "}
    assert len(validate_bank([item, duplicate], [record])) == 1


def test_malformed_url_is_skipped(tmp_path):
    record, _ = fixture(tmp_path)
    (tmp_path / "broken.jsonl").write_text(json.dumps({
        **record, "source_url": "https://[broken"}), encoding="utf-8")
    assert read_records(tmp_path) == [record]


def run_cli(clean_dir, candidates, output):
    with patch.object(sys, "argv", ["quiz", "--clean-dir", str(clean_dir),
                                   "--candidates", str(candidates), "--output", str(output)]):
        main()


def cli_fixture(tmp_path, count=5):
    clean = tmp_path / "clean"
    clean.mkdir()
    _, item = fixture(clean)
    candidates = tmp_path / "candidates.json"
    candidates.write_text(json.dumps([
        {**item, "id": f"q-{index}", "question": f"Question {index}: when was AITM established?"}
        for index in range(count)]), encoding="utf-8")
    return clean, candidates, clean / "quiz.jsonl"


def test_failed_minimum_preserves_existing_bank(tmp_path):
    clean, candidates, output = cli_fixture(tmp_path, count=1)
    output.write_text("previous reviewed bank\n", encoding="utf-8")
    with pytest.raises(SystemExit) as failure:
        run_cli(clean, candidates, output)
    assert failure.value.code == 1
    assert output.read_text(encoding="utf-8") == "previous reviewed bank\n"
    assert not list(clean.glob(".quiz-*.tmp"))


@pytest.mark.parametrize("target", ["source", "candidates"])
def test_cli_rejects_input_collision(tmp_path, target):
    clean, candidates, _ = cli_fixture(tmp_path)
    output = clean / "campus.jsonl" if target == "source" else candidates
    before = output.read_bytes()
    with pytest.raises(SystemExit) as failure:
        run_cli(clean, candidates, output)
    assert failure.value.code == 2
    assert output.read_bytes() == before


def test_atomic_output_is_repeatable_and_cleans_temporary_files(tmp_path):
    clean, candidates, output = cli_fixture(tmp_path)
    run_cli(clean, candidates, output)
    before = output.read_bytes()
    run_cli(clean, candidates, output)
    assert output.read_bytes() == before
    assert len(load_bank(output, clean)) == 5
    assert not list(clean.glob(".quiz-*.tmp"))


def test_replace_failure_preserves_bank_and_cleans_temporary_files(tmp_path):
    clean, candidates, output = cli_fixture(tmp_path)
    output.write_text("previous reviewed bank\n", encoding="utf-8")
    with patch("backend.quiz.generate.os.replace", side_effect=OSError("replace failed")):
        with pytest.raises(OSError, match="replace failed"):
            run_cli(clean, candidates, output)
    assert output.read_text(encoding="utf-8") == "previous reviewed bank\n"
    assert not list(clean.glob(".quiz-*.tmp"))
