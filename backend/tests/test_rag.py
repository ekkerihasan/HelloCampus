"""T1.3: ingest, retrieve with sources, min-score refusal, idempotent re-ingest, router, opt-in gate."""
import json
from pathlib import Path

import pytest

from backend.llm.client import OllamaClient
from backend.rag import ingest
from backend.rag.router import route_rules
from backend.rag.store import VectorStore, chunk_words, confident, sources_for
from backend.tests.fixtures import FIXTURE_RECORDS
from scraper.normalize import Record, write_jsonl


@pytest.fixture
async def store(tmp_path: Path):
    llm = await OllamaClient().check()
    vs = VectorStore(llm, tmp_path / "chroma")
    for col, recs in FIXTURE_RECORDS.items():
        await vs.ingest(col, recs)
    yield vs
    await llm.aclose()


async def test_relevant_question_returns_sources(store: VectorStore) -> None:
    hits = confident(await store.retrieve("When is the library open on Saturday?", ["campus"]))
    assert hits, "expected a confident hit"
    srcs = sources_for(hits)
    assert srcs[0].url == "https://example.org/fixture/library"


async def test_nonsense_question_refused(store: VectorStore) -> None:
    for q in ("purple elephant quantum banana", "What is the capital of Mongolia?"):
        assert confident(await store.retrieve(q, ["campus", "achievements"])) == []


async def test_reingest_is_idempotent(store: VectorStore) -> None:
    before = store.cols["campus"].count()
    await store.ingest("campus", FIXTURE_RECORDS["campus"])
    assert store.cols["campus"].count() == before
    await store.ingest("campus", FIXTURE_RECORDS["campus"][:1])
    assert store.cols["campus"].count() == 1


def test_chunking_overlap() -> None:
    text = " ".join(f"w{i}" for i in range(1000))
    chunks = chunk_words(text, tokens=100, overlap=20)
    assert len(chunks) > 1
    first, second = chunks[0].split(), chunks[1].split()
    assert first[-15:] == second[:15]  # 20 tokens is about 15 words
    assert chunks[-1].split()[-1] == "w999"


def test_router_rules() -> None:
    assert route_rules("Where can I get good lunch nearby?") == ["locality"]
    assert "students" in route_rules("I'm hiring a frontend intern")
    assert "achievements" in route_rules("Which teams won a hackathon?")
    assert route_rules("hmm") == []


async def test_only_optin_students_indexed(tmp_path: Path) -> None:
    clean = tmp_path / "clean"
    recs = [Record(id=f"students-{u}", collection="students", title=u, text=f"{u} builds things",
                   source_url=f"https://example.org/{u}", last_checked="2026-10-19", entity_id=u)
            for u in ("optedin", "notoptedin")]
    write_jsonl(recs, clean / "students.jsonl")
    optin = tmp_path / "optin.csv"
    optin.write_text("name,github_username,headline,consent\nA,optedin,,yes\nB,notoptedin,,no\n")
    loc = tmp_path / "loc.json"
    loc.write_text(json.dumps([{"id": "food-001", "type": "food", "name": "P", "last_checked": "2026-10-01",
                                "placeholder": True}]))
    llm = await OllamaClient().check()
    vs = VectorStore(llm, tmp_path / "chroma")
    counts = await ingest.ingest_all(vs, clean, loc, optin)
    await llm.aclose()
    assert counts["students"] == 1 and counts["locality"] == 0  # placeholders never ingested
    ids = vs.cols["students"].get(include=["metadatas"])["metadatas"]
    assert {m["entity_id"] for m in ids} == {"optedin"}
