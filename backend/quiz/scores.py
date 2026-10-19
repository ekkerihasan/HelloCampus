"""SQLite scores; leaderboard days use UTC."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class ScoreStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS quiz_scores (name TEXT NOT NULL, mode TEXT NOT NULL, score INTEGER NOT NULL, ts REAL NOT NULL, game_id TEXT NOT NULL, player INTEGER NOT NULL, UNIQUE(game_id, player))")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def save(self, game_id, mode, names, scores, now_ms):
        with self.connect() as db:
            db.executemany("INSERT OR IGNORE INTO quiz_scores(name,mode,score,ts,game_id,player) VALUES(?,?,?,?,?,?)",
                           [(name, mode, score, now_ms / 1000, game_id, i)
                            for i, (name, score) in enumerate(zip(names, scores))])

    def leaderboard(self, mode, now_ms):
        now = datetime.fromtimestamp(now_ms / 1000, timezone.utc)
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        with self.connect() as db:
            rows = db.execute("SELECT name,mode,score,ts FROM quiz_scores WHERE mode=? AND ts>=? AND ts<? ORDER BY score DESC,ts ASC,name ASC LIMIT 10",
                              (mode, midnight, midnight + 86400)).fetchall()
        return [dict(name=name, mode=mode, score=score, ts=ts) for name, mode, score, ts in rows]
