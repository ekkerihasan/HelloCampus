"""T4.1: the quiz bank post-check drops ungrounded items (ADDENDUM-03 section 4). Synthetic fixtures only."""
from backend.quiz.bank import QuizItem, post_check
from scraper.normalize import Record

URL = "https://example.org/fixture/library"
RECORDS = {URL: Record(id="campus-fx", collection="campus", title="Fixture library",
                       text="The central library holds\n30,000+ books and opens at 8 am on weekdays.",
                       source_url=URL, last_checked="2026-10-19")}


def item(**kw) -> QuizItem:
    base = dict(id="quiz-1", question="How many books does the library hold?",
                options=["30,000+", "5,000", "1 million", "200"], answer_index=0, source_url=URL,
                evidence="The central library holds 30,000+ books")
    return QuizItem(**{**base, **kw})


def test_grounded_item_passes_across_line_breaks():
    assert post_check(item(), RECORDS) is None


def test_evidence_not_in_record_is_dropped():
    assert post_check(item(evidence="The library holds 50,000 books"), RECORDS) == \
        "evidence is not a verbatim quote of the record"


def test_unknown_url_is_dropped():
    assert post_check(item(source_url="https://fake.invalid/page"), RECORDS) == "source URL not in stored data"


def test_correct_option_must_appear_in_evidence():
    assert post_check(item(answer_index=1), RECORDS) == "correct option does not appear in the evidence"


def test_ambiguous_options_are_dropped():
    bad = item(options=["30,000+", "books", "1 million", "200"], evidence="The central library holds 30,000+ books")
    assert post_check(bad, RECORDS) == "more than one option appears in the evidence"


def test_bare_number_evidence_is_dropped():
    assert post_check(item(question="How many books?", options=["30,000+", "5,000", "1 million", "200"],
                           evidence="30,000+"), RECORDS) == "evidence too short to prove the answer"


def test_duplicate_options_rejected():
    import pytest
    with pytest.raises(ValueError):
        item(options=["A", "a", "B", "C"])


async def test_game_scores_and_leaderboard_persist(tmp_path, monkeypatch):
    import httpx
    from backend.app import app
    from backend.config import settings
    from backend.routes import quiz as quiz_routes
    monkeypatch.setattr(settings, "quiz_scores_path", tmp_path / "scores.sqlite3")
    monkeypatch.setattr(quiz_routes, "_db", None)
    bank = [item(id=f"quiz-{i}") for i in range(6)]
    monkeypatch.setattr(quiz_routes, "load_bank", lambda: bank)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.get("/api/quiz/config")).json()["enabled"] is True
        assert len((await c.get("/api/quiz/game")).json()) == settings.quiz_questions_per_game
        await c.post("/api/quiz/score", json={"name": "Asha", "score": 540})
        board = (await c.post("/api/quiz/score", json={"name": "Ravi", "score": 720})).json()
    assert [r["name"] for r in board] == ["Ravi", "Asha"]
    monkeypatch.setattr(quiz_routes, "_db", None)  # a restart: the leaderboard comes back from SQLite
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        assert [r["score"] for r in (await c.get("/api/quiz/leaderboard")).json()] == [720, 540]
