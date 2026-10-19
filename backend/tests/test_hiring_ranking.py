"""Evidence coverage precedes retrieval order, model order and repository volume."""
import json

import pytest

from backend.config import settings
from backend.hiring import service
from backend.memory.store import RoleSpec
from backend.rag.store import Hit
from scraper.normalize import Record


def record(key, text, suffix="repo"):
    return Record(id=f"{key}-{suffix}", collection="students", entity_id=key, title=f"{key} project",
                  text=text, source_url=f"https://github.com/{key}/{suffix}", last_checked="2026-10-19")


def hit(key):
    return Hit(entity_id=key, text="project", title="project", source_url=f"https://github.com/{key}",
               collection="students", score=0.9)


def test_all_students_compared_before_limit_and_required_skills_win(monkeypatch):
    monkeypatch.setattr(settings, "hiring_candidate_limit", 1)
    grouped = {"popular": [record("popular", "React CSS Git Docker")],
               "best": [record("best", "React TypeScript")],
               "unrelated": [record("unrelated", "Photography")]}
    role = RoleSpec(title="Frontend", must_have=["React", "TypeScript"], nice_to_have=["CSS", "Git", "Docker"])
    assert service.shortlist_for_role(grouped, role, [hit("popular")] * 10) == ["best"]


@pytest.mark.parametrize("skill,text,expected", [
    ("Java", "JavaScript", False), ("C", "C++", False), ("C++", "C++ game", True),
    ("React", "React.js application", True), ("Node.js", "NodeJS API", True),
    ("React", "preact app", False), ("", "anything", False),
])
def test_skill_boundaries_and_aliases(skill, text, expected):
    assert service._skill_hit(skill, text) is expected


async def test_rank_is_server_owned_and_missing_requirements_are_explicit(monkeypatch):
    grouped = {"partial": [record("partial", "React")], "best": [record("best", "React TypeScript")]}
    monkeypatch.setattr(service, "student_data", lambda: grouped)
    monkeypatch.setattr(service, "optin_usernames", lambda: set(grouped))
    monkeypatch.setattr(service, "load_optin", lambda: [])

    class Rag:
        async def retrieve(self, *args, **kwargs):
            return [hit("partial")] * 10

    class LLM:
        async def chat_json(self, messages, temperature=None):
            return {"candidates": [
                {"entity_id": key, "claims": [{"text": "Stored React project", "url": grouped[key][0].source_url}]}
                for key in ("partial", "best", "best")
            ]}

    result = await service.match(LLM(), Rag(), RoleSpec(must_have=["React", "TypeScript"]))
    assert [c.entity_id for c in result] == ["best", "partial"]
    assert result[0].matched_must_have == ["React", "TypeScript"]
    assert result[1].missing_must_have == ["TypeScript"]


async def test_revocation_during_model_call_and_bounded_evidence(monkeypatch):
    grouped = {"student": [record("student", "unrelated", f"other{i}") for i in range(8)]
               + [record("student", "React project", "relevant")]}
    monkeypatch.setattr(service, "student_data", lambda: grouped)
    monkeypatch.setattr(service, "optin_usernames", lambda: set())
    monkeypatch.setattr(service, "load_optin", lambda: [])
    monkeypatch.setattr(settings, "hiring_records_per_candidate", 1)

    class Rag:
        async def retrieve(self, *args, **kwargs):
            return []

    class LLM:
        async def chat_json(self, messages, temperature=None):
            context = json.loads(messages[-1].content.split("\nEvidence: ", 1)[1])
            assert len(context["student"]) == 1
            assert context["student"][0]["text"] == "React project"
            return {"candidates": [{"entity_id": "student", "claims": [
                {"text": "React project", "url": grouped["student"][-1].source_url}]}]}

    assert await service.match(LLM(), Rag(), RoleSpec(must_have=["React"])) == []


async def test_unrelated_students_do_not_trigger_inference(monkeypatch):
    monkeypatch.setattr(service, "student_data", lambda: {"other": [record("other", "Photography")]})

    class Rag:
        async def retrieve(self, *args, **kwargs):
            return []

    class LLM:
        async def chat_json(self, *args, **kwargs):
            pytest.fail("unrelated evidence must not trigger inference")

    assert await service.match(LLM(), Rag(), RoleSpec(must_have=["Rust"])) == []
