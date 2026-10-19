import json
from types import SimpleNamespace

import pytest

from backend.quiz.engine import QuizEngine, QuizError
from backend.quiz.scores import ScoreStore


def setup(tmp_path):
    record = dict(collection="campus", source_url="https://aitm.edu.in/about/",
                  text="The correct answer is Alpha for this synthetic test.")
    (tmp_path / "campus.jsonl").write_text(json.dumps(record), encoding="utf-8")
    items = [dict(id=str(i), question=f"Synthetic question {i}?", options=["Alpha", "Beta", "Gamma", "Delta"],
                  answer_index=0, source_url=record["source_url"], evidence=record["text"]) for i in range(5)]
    bank = tmp_path / "quiz.jsonl"
    bank.write_text("\n".join(map(json.dumps, items)), encoding="utf-8")
    settings = SimpleNamespace(enabled=True, clean_dir=tmp_path, bank_path=bank,
                               sqlite_path=tmp_path / "scores.sqlite3", questions_per_game=5,
                               min_questions=5, answer_s=10, coop_answer_s=20,
                               hold_ms=500, streak_bonus=1, max_sessions=128, session_ttl_s=1800)
    now = [1700000000000]
    return QuizEngine(settings, lambda: now[0]), settings, now


def test_full_versus_persists_once(tmp_path):
    engine, settings, now = setup(tmp_path)
    state = engine.start("versus", ["One", "Two"])
    sid = state["id"]
    for _ in range(5):
        assert set(state["question"]) == {"id", "question", "options"}
        engine.action(sid, "buzz", player=0)
        state = engine.action(sid, "answer", player=0, option=0)
        assert state["phase"] == "reveal"
        assert state["question"]["answer_index"] == 0
        state = engine.action(sid, "next")
    assert state["phase"] == "finished" and state["question"] is None
    assert state["scores"] == [5, 0]
    engine.action(sid, "next")
    restarted = QuizEngine(settings, lambda: now[0])
    assert len(restarted.leaderboard("versus")) == 2
    assert restarted.leaderboard("versus")[0]["score"] == 5


def test_versus_wrong_and_timeout_pass(tmp_path):
    engine, _, now = setup(tmp_path)
    sid = engine.start("versus", ["One", "Two"])["id"]
    engine.action(sid, "buzz", player=0)
    state = engine.action(sid, "answer", player=0, option=1)
    assert state["active_player"] == 1
    now[0] += 10000
    assert engine.view(sid)["phase"] == "reveal"
    engine.action(sid, "next")
    engine.action(sid, "buzz", player=1)
    now[0] += 10000
    state = engine.view(sid)
    assert state["active_player"] == 0 and state["remaining_ms"] == 10000
    now[0] += 10000
    assert engine.view(sid)["phase"] == "reveal"


def test_full_coop_hold_disagreement_streak_and_restart(tmp_path):
    engine, settings, now = setup(tmp_path)
    sid = engine.start("coop", ["One", "Two"])["id"]
    engine.action(sid, "answer", player=0, option=0)
    state = engine.action(sid, "answer", player=1, option=1)
    assert state["hold_remaining_ms"] is None
    now[0] += 1000
    assert engine.view(sid)["phase"] == "coop"
    for _ in range(5):
        engine.action(sid, "answer", player=0, option=0)
        state = engine.action(sid, "answer", player=1, option=0)
        assert state["hold_remaining_ms"] == 500
        now[0] += 499
        assert engine.view(sid)["phase"] == "coop"
        now[0] += 1
        assert engine.view(sid)["phase"] == "reveal"
        state = engine.action(sid, "next")
    assert state["team_score"] == 15 and state["streak"] == 5
    board = QuizEngine(settings, lambda: now[0]).leaderboard("coop")
    assert board[0]["name"] == "One + Two" and board[0]["score"] == 15


def test_coop_hold_reset_timeout_and_wrong(tmp_path):
    engine, _, now = setup(tmp_path)
    sid = engine.start("coop", ["One", "Two"])["id"]
    for p in (0, 1):
        engine.action(sid, "answer", player=p, option=0)
    now[0] += 400
    engine.action(sid, "answer", player=1, option=1)
    now[0] += 500
    assert engine.view(sid)["phase"] == "coop"
    engine.action(sid, "answer", player=0, option=1)
    now[0] += 500
    state = engine.view(sid)
    assert state["phase"] == "reveal" and state["streak"] == 0
    engine.action(sid, "next")
    now[0] += 20000
    assert engine.view(sid)["phase"] == "reveal"


def test_bad_indices_empty_bank_and_session_limits(tmp_path):
    engine, settings, now = setup(tmp_path)
    sid = engine.start("versus", ["One", "Two"])["id"]
    with pytest.raises(QuizError):
        engine.action(sid, "buzz", player=True)
    engine.action(sid, "buzz", player=0)
    with pytest.raises(QuizError):
        engine.action(sid, "answer", player=0, option=True)
    settings.max_sessions = 1
    with pytest.raises(QuizError) as exc:
        engine.start("coop", ["One", "Two"])
    assert exc.value.status == 503
    now[0] += 1800001
    assert engine.start("coop", ["One", "Two"])["phase"] == "coop"
    settings.bank_path.write_text("", encoding="utf-8")
    assert engine.config()["ready"] is False
    with pytest.raises(QuizError) as exc:
        engine.start("coop", ["One", "Two"])
    assert exc.value.message == "Quiz needs more campus data"


def test_missing_and_corrupt_bank(tmp_path):
    engine, settings, _ = setup(tmp_path)
    settings.bank_path.unlink()
    assert engine.config()["ready"] is False
    assert engine.config()["questions_available"] == 0
    with pytest.raises(QuizError) as exc:
        engine.start("coop", ["One", "Two"])
    assert exc.value.status == 503
    assert exc.value.message == "Quiz needs more campus data"
    settings.bank_path.write_bytes(b"\xff\xfe")
    assert engine.config()["ready"] is False
    with pytest.raises(QuizError) as exc:
        engine.start("versus", ["One", "Two"])
    assert exc.value.status == 503


def test_tick_preserves_revision_until_transition_and_late_hold_wins(tmp_path):
    engine, _, now = setup(tmp_path)
    state = engine.start("coop", ["One", "Two"])
    sid = state["id"]
    assert engine.action(sid, "tick")["revision"] == state["revision"]
    now[0] += 19000
    engine.action(sid, "answer", player=0, option=0)
    state = engine.action(sid, "answer", player=1, option=0)
    # Poll after the deadline; the hold actually completed 500 ms beforehand.
    now[0] += 2000
    result = engine.action(sid, "tick")
    assert result["phase"] == "reveal" and result["team_score"] == 1
    assert result["revision"] > state["revision"]
    assert engine.action(sid, "tick")["revision"] == result["revision"]


def test_score_connections_close_on_success_and_failure(tmp_path, monkeypatch):
    store = ScoreStore(tmp_path / "test.sqlite3")
    import backend.quiz.scores as scores_module
    original = scores_module.sqlite3.connect
    connections = []

    def tracked(*args, **kwargs):
        connection = original(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(scores_module.sqlite3, "connect", tracked)
    store.leaderboard("coop", 1700000000000)
    with pytest.raises(RuntimeError):
        with store.connect():
            raise RuntimeError("intentional failure")
    assert len(connections) == 2
    for connection in connections:
        with pytest.raises(scores_module.sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")
