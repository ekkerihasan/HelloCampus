"""SQLite visitor memory: profile facts, last N turns, shortlist. Resume on any device with a short code.
Full transcripts are never kept: turns beyond MEMORY_MAX_TURNS are deleted on every write."""
import json
import secrets
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from pydantic import BaseModel, Field

from backend.config import settings
from backend.llm.client import ChatMessage

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I/L
PURPOSES = ("Session or talk", "Judging or mentoring", "Hiring", "Event", "Parent or alumni", "Just visiting")

SCHEMA = """
CREATE TABLE IF NOT EXISTS visitors (
  id TEXT PRIMARY KEY, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL, purpose TEXT NOT NULL DEFAULT '',
  facts TEXT NOT NULL DEFAULT '{}', role TEXT NOT NULL DEFAULT '{}', summary TEXT NOT NULL DEFAULT '',
  character TEXT NOT NULL DEFAULT 'guide', created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS turns (
  id INTEGER PRIMARY KEY AUTOINCREMENT, visitor_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS shortlist (
  visitor_id TEXT NOT NULL, entity_id TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', added_at REAL NOT NULL,
  PRIMARY KEY (visitor_id, entity_id)
);
"""


class RoleSpec(BaseModel):
    title: str = ""
    must_have: list[str] = []
    nice_to_have: list[str] = []
    level: str = ""
    mode: str = ""  # remote | onsite | hybrid


class Visitor(BaseModel):
    id: str
    code: str
    name: str
    purpose: str = ""
    facts: dict = Field(default_factory=dict)  # preferences, plans, interests: list[str] each
    role: RoleSpec = Field(default_factory=RoleSpec)
    summary: str = ""
    character: str = "guide"
    shortlist: list[str] = []


class MemoryStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path or settings.sqlite_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(SCHEMA)
        self.status_detail = f"sqlite {self.path.name}"

    def _new_code(self) -> str:
        while True:
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(settings.resume_code_length))
            if not self._db.execute("SELECT 1 FROM visitors WHERE code=?", (code,)).fetchone():
                return code

    def create(self, name: str, purpose: str = "") -> Visitor:
        now = time.time()
        with self._lock:
            vid, code = uuid.uuid4().hex, self._new_code()
            self._db.execute("INSERT INTO visitors (id, code, name, purpose, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                             (vid, code, name.strip(), purpose.strip(), now, now))
            self._db.commit()
        return self.get(vid)  # type: ignore[return-value]

    def _row_to_visitor(self, row: sqlite3.Row) -> Visitor:
        sl = [r["entity_id"] for r in self._db.execute(
            "SELECT entity_id FROM shortlist WHERE visitor_id=? ORDER BY added_at", (row["id"],))]
        return Visitor(id=row["id"], code=row["code"], name=row["name"], purpose=row["purpose"],
                       facts=json.loads(row["facts"]), role=RoleSpec(**json.loads(row["role"])),
                       summary=row["summary"], character=row["character"], shortlist=sl)

    def get(self, visitor_id: str) -> Visitor | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM visitors WHERE id=?", (visitor_id,)).fetchone()
            return self._row_to_visitor(row) if row else None

    def by_code(self, code: str) -> Visitor | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM visitors WHERE code=?", (code.strip().upper(),)).fetchone()
            return self._row_to_visitor(row) if row else None

    def update(self, visitor_id: str, **fields) -> Visitor | None:
        allowed = {"name", "purpose", "facts", "role", "summary", "character"}
        sets, vals = [], []
        for k, v in fields.items():
            if k not in allowed or v is None:
                continue
            if isinstance(v, BaseModel):
                v = v.model_dump()
            sets.append(f"{k}=?")
            vals.append(json.dumps(v) if isinstance(v, (dict, list)) else v)
        if sets:
            with self._lock:
                self._db.execute(f"UPDATE visitors SET {', '.join(sets)}, updated_at=? WHERE id=?",
                                 (*vals, time.time(), visitor_id))
                self._db.commit()
        return self.get(visitor_id)

    def add_turn(self, visitor_id: str, role: str, content: str) -> None:
        with self._lock:
            self._db.execute("INSERT INTO turns (visitor_id, role, content, created_at) VALUES (?,?,?,?)",
                             (visitor_id, role, content, time.time()))
            # Keep only the last N turns (a turn here is one message).
            self._db.execute(
                "DELETE FROM turns WHERE visitor_id=? AND id NOT IN "
                "(SELECT id FROM turns WHERE visitor_id=? ORDER BY id DESC LIMIT ?)",
                (visitor_id, visitor_id, settings.memory_max_turns))
            self._db.commit()

    def history(self, visitor_id: str) -> list[ChatMessage]:
        with self._lock:
            rows = self._db.execute("SELECT role, content FROM turns WHERE visitor_id=? ORDER BY id", (visitor_id,))
            return [ChatMessage(role=r["role"], content=r["content"]) for r in rows]

    def shortlist_add(self, visitor_id: str, entity_id: str, note: str = "") -> list[str]:
        with self._lock:
            self._db.execute("INSERT OR IGNORE INTO shortlist (visitor_id, entity_id, note, added_at) VALUES (?,?,?,?)",
                             (visitor_id, entity_id, note, time.time()))
            self._db.commit()
        return self.get(visitor_id).shortlist  # type: ignore[union-attr]

    def shortlist_remove(self, visitor_id: str, entity_id: str) -> list[str]:
        with self._lock:
            self._db.execute("DELETE FROM shortlist WHERE visitor_id=? AND entity_id=?", (visitor_id, entity_id))
            self._db.commit()
        return self.get(visitor_id).shortlist  # type: ignore[union-attr]


def visitor_block(v: Visitor | None) -> str:
    """Compact facts injected into every system prompt."""
    if v is None:
        return ""
    lines = [f"Name: {v.name}"]
    if v.purpose:
        lines.append(f"Here for: {v.purpose}")
    for key, items in v.facts.items():
        if items:
            lines.append(f"{key.replace('_', ' ').capitalize()}: {', '.join(map(str, items)) if isinstance(items, list) else items}")
    if v.role.title:
        lines.append(f"Hiring for: {v.role.title} (must have: {', '.join(v.role.must_have) or 'n/a'})")
    if v.shortlist:
        lines.append(f"Shortlisted students: {', '.join(v.shortlist)}")
    if v.summary:
        lines.append(f"So far: {v.summary}")
    return "What I know about this visitor (use it to personalise, do not repeat it back):\n" + "\n".join(lines)
