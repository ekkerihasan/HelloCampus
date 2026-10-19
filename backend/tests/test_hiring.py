"""Synthetic student fixtures test evidence rejection and current consent on every route."""
from pathlib import Path

import httpx
import pytest

from backend.app import app
from backend.config import settings
from backend.hiring import service
from backend.memory.store import MemoryStore
from backend.rag.store import Hit
from backend.status import registry
from scraper.normalize import Record, write_jsonl

URL = "https://github.com/fixture-student/project"


class HiringLLM:
    async def chat_json(self, messages, temperature=None):
        prompt = messages[0].content
        if "Extract a hiring" in prompt:
            return {"title": "Frontend intern", "must_have": ["React"], "nice_to_have": [], "level": "intern", "mode": ""}
        if "five interview" in prompt:
            return {"questions": [{"text": f"Explain part {i} of your repository?", "url": URL} for i in range(5)]}
        return {"candidates": [{"entity_id": "fixture-student", "claims": [
            {"text": "Built a React project", "url": URL},
            {"text": "Invented achievement", "url": "https://fake.invalid/award"}]}]}

    async def chat(self, messages, temperature=None):
        return f"# Fixture Student\n[Project]({URL})\n[Invented](https://fake.invalid/profile)"


class HiringRAG:
    async def retrieve(self, question, collections):
        return [Hit(text="React project", title="Fixture project", source_url=URL,
                    collection="students", score=0.9, entity_id="fixture-student")]


@pytest.fixture
async def hiring_api(tmp_path: Path, monkeypatch):
    clean = tmp_path / "clean"
    optin = tmp_path / "optin.csv"
    optin.write_text("name,github_username,consent\nFixture Student,fixture-student,yes\n")
    monkeypatch.setattr(settings, "clean_dir", clean)
    monkeypatch.setattr(settings, "students_optin_path", optin)
    r = Record(id="fixture-profile", collection="students", title="Synthetic student",
        text="Fixture Student built a React project", source_url=URL, last_checked="2026-10-19",
        entity_id="fixture-student", extra={"kind": "profile", "name": "Fixture Student",
            "top_languages": ["TypeScript"], "profile_readme": "Old fixture README"})
    write_jsonl([r], clean / "students.jsonl")
    mem = MemoryStore(tmp_path / "memory.db")
    v = mem.create("Fixture Recruiter", "Hiring")
    components = {"memory": mem, "llm": HiringLLM(), "rag": HiringRAG()}
    monkeypatch.setattr(registry, "get", components.get)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, v, optin, r
    mem.close()


async def test_role_match_and_unknown_url_removed(hiring_api):
    client, v, _, _ = hiring_api
    res = await client.post("/api/hiring/role", json={"visitor_id": v.id, "description": "React frontend intern"})
    assert res.status_code == 200 and res.json()["must_have"] == ["React"]
    res = await client.post("/api/hiring/match", json={"visitor_id": v.id})
    assert res.status_code == 200
    assert res.json()[0]["claims"] == [{"text": "Built a React project", "url": URL}]
    assert "fake.invalid" not in res.text


async def test_shortlist_compare_export_and_revocation(hiring_api):
    client, v, optin, _ = hiring_api
    added = await client.post("/api/hiring/shortlist", json={"visitor_id": v.id, "entity_id": "fixture-student"})
    assert added.json() == ["fixture-student"]
    assert (await client.get(f"/api/hiring/shortlist/{v.id}")).json()[0]["name"] == "Fixture Student"
    exported = await client.get(f"/api/hiring/export/{v.id}")
    assert URL in exported.text and "attachment" in exported.headers["content-disposition"]
    compared = await client.post("/api/hiring/compare", json={"entity_ids": ["fixture-student", "fixture-student"]})
    assert compared.status_code == 200
    optin.write_text("name,github_username,consent\nFixture Student,fixture-student,no\n")
    assert (await client.get(f"/api/hiring/shortlist/{v.id}")).json() == []
    assert (await client.get(f"/api/visitor/{v.id}")).json()["shortlist"] == []
    assert (await client.get("/api/students/fixture-student")).status_code == 404
    assert URL not in (await client.get(f"/api/hiring/export/{v.id}")).text
    assert (await client.post("/api/students/fixture-student/readme")).status_code == 404


async def test_interview_and_readme_before_after(hiring_api):
    client, _, _, _ = hiring_api
    questions = await client.post("/api/hiring/interview/fixture-student")
    assert questions.status_code == 200 and len(questions.json()) == 5
    readme = (await client.post("/api/students/fixture-student/readme")).json()
    assert readme["before"] == "Old fixture README"
    assert URL in readme["after"] and "fake.invalid" not in readme["after"]


def test_hidden_unknown_url_in_claim_rejected():
    r = Record(id="fixture", collection="students", title="Fixture", text="Synthetic",
               source_url=URL, last_checked="2026-10-19")
    assert service.filter_claims([{"text": "Read https://fake.invalid/award", "url": URL}], [r]) == []
