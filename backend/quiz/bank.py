"""Read only public campus snapshots and validate every persisted question."""

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class QuizItem:
    id: str
    question: str
    options: list[str]
    answer_index: int
    source_url: str
    evidence: str

    def to_dict(self) -> dict:
        return asdict(self)


def read_records(clean_dir: Path) -> list[dict]:
    records = []
    for path in sorted(clean_dir.glob("*.jsonl")):
        if path.name == "quiz.jsonl":
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except (ValueError, TypeError):
                continue
            if not isinstance(record, dict):
                continue
            url = record.get("source_url", "")
            extra = record.get("extra") or {}
            if not isinstance(url, str) or not isinstance(extra, dict):
                continue
            try:
                parsed = urlparse(url)
                hostname = parsed.hostname
            except ValueError:
                continue
            if (record.get("collection") not in {"campus", "achievements"}
                    or record.get("private") or extra.get("private")
                    or record.get("placeholder") or extra.get("placeholder")
                    or hostname not in {"aitm.edu.in", "www.aitm.edu.in"}
                    or parsed.scheme != "https"
                    or not isinstance(record.get("text"), str)):
                continue
            records.append(record)
    return records


def validate_item(raw: Any, records: list[dict]) -> QuizItem | None:
    if not isinstance(raw, dict):
        return None
    for key in ("id", "question", "source_url", "evidence"):
        if not isinstance(raw.get(key), str) or not raw[key].strip():
            return None
    options, answer = raw.get("options"), raw.get("answer_index")
    if (not isinstance(options, list) or len(options) != 4
            or any(not isinstance(option, str) or not option.strip() for option in options)
            or len({option.strip().casefold() for option in options}) != 4
            or type(answer) is not int or not 0 <= answer < 4):
        return None
    evidence = raw["evidence"]
    if len(evidence.strip()) < 12 or not any(c.isalpha() for c in evidence):
        return None
    if options[answer] not in evidence:
        return None
    if not any(record["source_url"] == raw["source_url"]
               and evidence in record["text"] for record in records):
        return None
    return QuizItem(**{key: raw[key] for key in QuizItem.__dataclass_fields__})


def validate_bank(candidates: list, records: list[dict]) -> list[QuizItem]:
    result, ids, questions = [], set(), set()
    for raw in candidates:
        item = validate_item(raw, records)
        if item is None:
            continue
        question_key = " ".join(item.question.casefold().split())
        if item.id in ids or question_key in questions:
            continue
        ids.add(item.id)
        questions.add(question_key)
        result.append(item)
    return result


def load_bank(path: Path, clean_dir: Path) -> list[QuizItem]:
    if not path.is_file():
        return []
    candidates = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            candidates.append(json.loads(line))
        except ValueError:
            continue
    return validate_bank(candidates, read_records(clean_dir))
