"""T1.3/T1.4: ingest with hash cache, hybrid retrieval with RRF, refusal, BM25 exact names, valid_until, opt-in gate.
Uses the deterministic FakeEmbedder from conftest, so no embedding quota is spent."""
import json
from pathlib import Path

import pytest

from backend.config import settings
from backend.rag import ingest
from backend.rag.bm25 import BM25, tokenize
from backend.rag.router import route
from backend.rag.search import needs_translation, search_campus
from backend.rag.store import Hit, VectorStore, chunk_prose, chunk_words, confident, sources_for
from backend.tests.fixtures import FIXTURE_RECORDS
from scraper.normalize import Record, write_jsonl


@pytest.fixture
async def store(tmp_path: Path, embedder):
    vs = VectorStore(embedder, tmp_path / "chroma", tmp_path / "cache.sqlite3")
    for col, recs in FIXTURE_RECORDS.items():
        await vs.ingest(col, recs, whole=col != "campus")
    yield vs
    await vs.aclose()


async def test_relevant_question_returns_sources(store: VectorStore) -> None:
    r = await search_campus(store, None, "When is the library open on Saturday?", ["campus"])
    assert not r.refusal
    assert r.sources[0].url == "https://example.org/fixture/library"
    assert r.snippets[0].startswith("[1] Fixture Institute library hours")


async def test_nonsense_question_refused(store: VectorStore) -> None:
    for q in ("purple elephant quantum banana", "What is the capital of Mongolia?"):
        assert (await search_campus(store, None, q)).refusal


async def test_second_ingest_embeds_zero_chunks(store: VectorStore, embedder) -> None:
    before = embedder.texts
    stats = await store.ingest("campus", FIXTURE_RECORDS["campus"])
    assert stats.embedded == 0 and stats.cached == stats.chunks > 0
    assert embedder.texts == before
    changed = FIXTURE_RECORDS["campus"][0].model_copy(update={"text": "The library now opens at 7 am daily."})
    stats = await store.ingest("campus", [changed])
    assert stats.embedded == 1 and stats.removed >= 1  # only the changed chunk is embedded, the stale one removed
    assert store.cols["campus"].count() == 1


async def test_bm25_finds_exact_names_embeddings_miss(tmp_path: Path, embedder) -> None:
    vs = VectorStore(embedder, tmp_path / "chroma", tmp_path / "cache.sqlite3")
    recs = [Record(id=f"campus-n{i}", collection="campus", title=f"Hall {i}", text=t,
                   source_url=f"https://example.org/hall{i}", last_checked="2026-10-19")
            for i, t in enumerate(["Seminar talks happen in many rooms across the institute every week.",
                                   "The Zephyrine auditorium hosts guest lectures."])]
    await vs.ingest("campus", recs, whole=True)
    hits = await vs.retrieve("zephyrine", ["campus"])
    assert hits[0].source_url == "https://example.org/hall1"
    assert hits[0].keyword_coverage == 1.0 and confident(hits[:1])
    await vs.aclose()


async def test_expired_valid_until_is_filtered(tmp_path: Path, embedder) -> None:
    vs = VectorStore(embedder, tmp_path / "chroma", tmp_path / "cache.sqlite3")
    old = Record(id="campus-old", collection="campus", title="Robotics expo", text="Robotics expo in the main hall",
                 source_url="https://example.org/expo", last_checked="2026-01-01", extra={"valid_until": "2026-01-02"})
    await vs.ingest("campus", [old], whole=True)
    assert await vs.retrieve("robotics expo", ["campus"]) == []
    await vs.aclose()


async def test_only_optin_students_indexed_and_report(tmp_path: Path, embedder) -> None:
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
    vs = VectorStore(embedder, tmp_path / "chroma", tmp_path / "cache.sqlite3")
    stats = await ingest.ingest_all(vs, clean, loc, optin)
    assert stats["students"].chunks == 1 and stats["locality"].chunks == 0  # placeholders never ingested
    metas = vs.cols["students"].get(include=["metadatas"])["metadatas"]
    assert {m["entity_id"] for m in metas} == {"optedin"}
    report = ingest.write_report(stats, 5, {}, tmp_path / "report.json")
    assert report["totals"]["chunks"] == 1 and json.loads((tmp_path / "report.json").read_text())
    await vs.aclose()


async def test_collection_recreated_when_embed_model_changes(tmp_path: Path, embedder) -> None:
    vs = VectorStore(embedder, tmp_path / "chroma", tmp_path / "cache.sqlite3")
    await vs.ingest("campus", FIXTURE_RECORDS["campus"])
    await vs.aclose()
    embedder.embed_model = "another-model"
    vs2 = VectorStore(embedder, tmp_path / "chroma", tmp_path / "cache.sqlite3")
    assert vs2.cols["campus"].count() == 0  # incompatible vectors are never mixed
    await vs2.aclose()


def test_chunking_overlap_and_headings() -> None:
    text = " ".join(f"w{i}" for i in range(1000))
    chunks = chunk_words(text, tokens=100, overlap=20)
    assert chunks[0].split()[-15:] == chunks[1].split()[:15]
    assert chunks[-1].split()[-1] == "w999"
    prose = "# Library\n" + "books " * 200 + "\n# Sports\n" + "cricket " * 200
    parts = chunk_prose(prose)
    assert parts[0].startswith("# Library") and any(p.startswith("# Sports") for p in parts)


def test_bm25_tokenize_and_coverage() -> None:
    assert tokenize("Where are the Halls?") == ["hall"]
    idx = BM25(["a", "b"], ["main library hours", "cricket ground"])
    [(doc_id, _score, cov)] = idx.search("library hours", 5)
    assert doc_id == "a" and cov == 1.0


def test_router_rules_and_translation_detection() -> None:
    assert route("Where can I get good lunch nearby?") == ["locality"]
    assert "students" in route("I'm hiring a frontend intern")
    assert "achievements" in route("Which teams won a hackathon?")
    assert route("hmm") == ["campus", "achievements", "students", "locality"]
    assert needs_translation("लाइब्रेरी कब खुलती है?") and needs_translation("ಗ್ರಂಥಾಲಯ ಎಲ್ಲಿದೆ")
    assert not needs_translation("When does the library open? café")


def test_sources_deduplicated_with_citation_numbers() -> None:
    hits = [Hit(text="t", title="A", source_url=u, collection="campus") for u in
            ("https://example.org/a", "https://example.org/b", "https://example.org/a")]
    assert [(s.url, s.citations) for s in sources_for(hits)] == [
        ("https://example.org/a", [1, 3]), ("https://example.org/b", [2])]


def test_min_score_is_config_driven(monkeypatch) -> None:
    h = Hit(text="t", title="A", source_url="u", collection="campus", score=0.5, keyword_coverage=0.1)
    monkeypatch.setattr(settings, "rag_min_score", 0.4)
    assert confident([h])
    monkeypatch.setattr(settings, "rag_min_score", 0.9)
    assert not confident([h])


async def test_query_embeddings_are_cached_and_prefetched(store: VectorStore, embedder) -> None:
    calls = []
    original = embedder.embed_query

    async def counting(text):
        calls.append(text)
        return await original(text)

    embedder.embed_query = counting
    store.prefetch("When is the library open?")
    await store.retrieve("When is the library open?", ["campus"])
    await store.retrieve("When is the library open?", ["campus"])
    assert calls == ["When is the library open?"]  # one embedding for prefetch plus two searches (M-008)


def test_derived_department_list_cites_each_real_page():
    """M-015: no page lists every department, so ingest derives one list; chips point at the real pages only."""
    from backend.rag.ingest import derived_records
    pages = [Record(id=f"campus-d{i}", collection="campus", title=f"{name} | AITM Bhatkal", text="x",
                    source_url=f"https://aitm.edu.in/departments/{slug}/", last_checked="2026-10-19")
             for i, (name, slug) in enumerate([("Civil Engineering", "civil"), ("Mechanical Engineering", "mech")])]
    [derived] = derived_records(pages + [Record(id="campus-x", collection="campus", title="About", text="y",
                                                source_url="https://aitm.edu.in/about/", last_checked="2026-10-19")])
    assert derived.text == ("AITM has these 2 departments, each with its own official page: Civil Engineering; "
                            "Mechanical Engineering.")
    assert derived.source_url == "derived:departments"
    hit = Hit(text=derived.text, title=derived.title, source_url=derived.source_url, collection="campus",
              sources="\n".join(f"{u}\t{t}" for u, t in derived.extra["sources"]))
    chips = sources_for([hit])
    assert [c.url for c in chips] == ["https://aitm.edu.in/departments/civil/", "https://aitm.edu.in/departments/mech/"]
    assert all(c.citations == [1] for c in chips) and not any(c.url.startswith("derived") for c in chips)
