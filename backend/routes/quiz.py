"""Buzzer Quiz API (ADDENDUM-03, ADDENDUM-04): a game from the pre-built bank, scores, the day's leaderboard.
No LLM call happens during play, so the game works offline and costs no quota."""
import asyncio
import random
import sqlite3
import threading
import time
from datetime import date, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.config import settings
from backend.quiz.bank import QuizItem, load_bank

router = APIRouter(prefix="/api/quiz")
_lock = threading.RLock()  # re-entrant: db() is called while the lock is held
_db: sqlite3.Connection | None = None


def db() -> sqlite3.Connection:
    global _db
    with _lock:
        if _db is None:
            settings.quiz_scores_path.parent.mkdir(parents=True, exist_ok=True)
            _db = sqlite3.connect(settings.quiz_scores_path, check_same_thread=False)
            _db.execute("CREATE TABLE IF NOT EXISTS quiz_scores (name TEXT NOT NULL, mode TEXT NOT NULL, "
                        "score INTEGER NOT NULL, ts REAL NOT NULL)")
            _db.commit()
        return _db


class QuizConfig(BaseModel):
    enabled: bool
    questions: int
    per_game: int
    answer_s: int
    points_correct: int
    time_bonus_per_s: int
    hold_ms: int


class ScoreIn(BaseModel):
    name: str = Field(min_length=1, max_length=30)  # typed by the player, never derived from the camera
    mode: str = Field("solo", pattern="^(solo|versus)$")
    score: int = Field(ge=0, le=10_000)


class ScoreRow(BaseModel):
    name: str
    mode: str
    score: int
    at: str


@router.get("/config", response_model=QuizConfig)
async def config() -> QuizConfig:
    bank = await asyncio.to_thread(load_bank) if settings.quiz_enabled else []
    return QuizConfig(enabled=settings.quiz_enabled and len(bank) >= settings.quiz_questions_per_game,
                      questions=len(bank), per_game=settings.quiz_questions_per_game,
                      answer_s=settings.quiz_solo_answer_s, points_correct=settings.quiz_points_correct,
                      time_bonus_per_s=settings.quiz_time_bonus_per_s, hold_ms=settings.gesture_hold_ms)


@router.get("/game", response_model=list[QuizItem])
async def game() -> list[QuizItem]:
    if not settings.quiz_enabled:
        raise HTTPException(503, "The quiz is turned off.")
    bank = await asyncio.to_thread(load_bank)
    if len(bank) < settings.quiz_questions_per_game:
        raise HTTPException(503, "Quiz needs more campus data.")
    return random.sample(bank, settings.quiz_questions_per_game)


def _today_rows(mode: str) -> list[ScoreRow]:
    start = datetime.combine(date.today(), datetime.min.time()).timestamp()
    with _lock:
        rows = db().execute("SELECT name, mode, score, ts FROM quiz_scores WHERE mode=? AND ts>=? "
                            "ORDER BY score DESC, ts ASC LIMIT ?", (mode, start, settings.quiz_leaderboard_size))
        return [ScoreRow(name=n, mode=m, score=s, at=datetime.fromtimestamp(t).strftime("%H:%M")) for n, m, s, t in rows]


@router.get("/leaderboard", response_model=list[ScoreRow])
async def leaderboard(mode: str = "solo") -> list[ScoreRow]:
    return await asyncio.to_thread(_today_rows, mode)


@router.post("/score", response_model=list[ScoreRow])
async def score(body: ScoreIn) -> list[ScoreRow]:
    def save() -> None:
        with _lock:
            db().execute("INSERT INTO quiz_scores (name, mode, score, ts) VALUES (?,?,?,?)",
                         (body.name.strip(), body.mode, body.score, time.time()))
            db().commit()
    await asyncio.to_thread(save)
    return await asyncio.to_thread(_today_rows, body.mode)
