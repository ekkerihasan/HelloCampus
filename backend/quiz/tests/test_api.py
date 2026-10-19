"""Exercise the isolated public HTTP contract without importing the core app."""
import json

from fastapi.testclient import TestClient
import pytest

from backend.quiz.api import create_app
from backend.quiz.config import QuizSettings
from backend.quiz.engine import QuizEngine


@pytest.fixture
def preview(tmp_path):
    text = "Synthetic test record says Alpha is the correct option."
    url = "https://aitm.edu.in/about/"
    (tmp_path / "campus.jsonl").write_text(json.dumps({"collection": "campus", "text": text,
        "source_url": url}), encoding="utf-8")
    bank = tmp_path / "quiz.jsonl"
    bank.write_text("\n".join(json.dumps({"id": str(i), "question": f"Synthetic fixture {i}?",
        "options": ["Alpha", "Beta", "Gamma", "Delta"], "answer_index": 0,
        "source_url": url, "evidence": text}) for i in range(5)), encoding="utf-8")
    settings = QuizSettings(_env_file=None, clean_dir=tmp_path, bank_path=bank,
                            sqlite_path=tmp_path / "quiz.sqlite3")
    now = [1700000000000]
    service = QuizEngine(settings, clock=lambda: now[0])
    with TestClient(create_app(settings, service)) as client:
        yield client, service, settings, now


def test_config_missing_bank_and_validation(preview):
    client, _, settings, _ = preview
    config = client.get("/api/quiz/config").json()
    assert config["ready"] and config["question_count"] == 5
    assert client.post("/api/quiz/start", json={"mode": "invalid", "players": ["A", "B"]}).status_code == 422
    assert client.post("/api/quiz/start", json={"mode": "versus", "players": [" ", "B"]}).status_code == 422
    settings.bank_path.unlink()
    assert client.get("/api/quiz/config").json()["ready"] is False
    assert client.post("/api/quiz/start", json={"mode": "versus", "players": ["A", "B"]}).status_code == 503


def test_http_versus_round_and_answer_secrecy(preview):
    client, _, _, _ = preview
    game = client.post("/api/quiz/start", json={"mode": "versus", "players": ["Test A", "Test B"]}).json()
    assert "answer_index" not in game["question"] and "evidence" not in game["question"]
    path = "/api/quiz/" + game["id"] + "/action"
    assert client.post(path, json={"action": "buzz", "player": True}).status_code == 422
    game = client.post(path, json={"action": "buzz", "player": 0}).json()
    assert game["active_player"] == 0
    assert client.post(path, json={"action": "answer", "player": 1, "option": 0}).status_code == 409
    game = client.post(path, json={"action": "answer", "player": 0, "option": 0, "score": 9999}).json()
    assert game["scores"] == [1, 0] and game["question"]["answer_index"] == 0
    assert game["question"]["source_url"] == "https://aitm.edu.in/about/"
    assert client.post(path, json={"action": "tick"}).status_code == 200
    assert client.get("/api/quiz/missing-session").status_code == 404


def test_full_coop_http_and_restart_leaderboard(preview):
    client, _, settings, now = preview
    game = client.post("/api/quiz/start", json={"mode": "coop", "players": ["Test A", "Test B"]}).json()
    path = "/api/quiz/" + game["id"] + "/action"
    for _ in range(5):
        client.post(path, json={"action": "answer", "player": 0, "option": 0})
        game = client.post(path, json={"action": "answer", "player": 1, "option": 0}).json()
        assert game["phase"] == "coop"
        now[0] += 500
        assert client.get("/api/quiz/" + game["id"]).json()["phase"] == "reveal"
        game = client.post(path, json={"action": "next"}).json()
    assert game["phase"] == "finished" and game["team_score"] == 15
    client.post(path, json={"action": "next"})
    restarted = QuizEngine(settings, clock=lambda: now[0])
    with TestClient(create_app(settings, restarted)) as second:
        scores = second.get("/api/quiz/leaderboard?mode=coop").json()["entries"]
    assert len(scores) == 1 and scores[0]["name"] == "Test A + Test B" and scores[0]["score"] == 15


def test_preview_cors_and_disabled_switch(preview):
    client, service, _, _ = preview
    res = client.options("/api/quiz/start", headers={"Origin": "http://localhost:5174",
        "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
    assert res.status_code == 200 and res.headers["access-control-allow-origin"] == "http://localhost:5174"
    service.settings.enabled = False
    assert client.get("/api/quiz/config").json()["enabled"] is False
    assert client.post("/api/quiz/start", json={"mode": "coop", "players": ["A", "B"]}).status_code == 503
