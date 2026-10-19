"""Independent quiz settings; no dependency on the mid-change core configuration."""
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class QuizSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QUIZ_", env_file=ROOT / ".env", extra="ignore")

    enabled: bool = True
    clean_dir: Path = ROOT / "data" / "clean"
    bank_path: Path = ROOT / "data" / "clean" / "quiz.jsonl"
    sqlite_path: Path = ROOT / "data" / "quiz.sqlite3"
    questions_per_game: int = Field(default=5, ge=1, le=50)
    min_questions: int = Field(default=5, ge=5, le=1000)
    answer_s: float = Field(default=10, gt=0, le=300)
    coop_answer_s: float = Field(default=20, gt=0, le=300)
    hold_ms: int = Field(default=500, ge=100, le=10000)
    streak_bonus: int = Field(default=1, ge=0, le=20)
    max_sessions: int = Field(default=128, ge=1, le=10000)
    session_ttl_s: float = Field(default=1800, ge=30, le=86400)
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173",
                               "http://localhost:5174", "http://127.0.0.1:5174"]
