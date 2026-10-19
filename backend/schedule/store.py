"""Schedule, venues and contacts in SQLite, plus locality rows mirrored for exact filters (ADDENDUM-01 7.1).
Exact answers only: similarity search never guesses a time. Source of truth is data/schedule.json and
data/locality.json (hand-curated). Placeholder rows are loaded for validation but never returned."""
import json
import sqlite3
import sys
import threading
from datetime import date as Date
from pathlib import Path

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from backend.config import settings
from backend.rag import locality


class Event(BaseModel):
    id: str = Field(pattern=r"^event-\d{3}$")
    title: str = Field(min_length=1)
    date: Date
    start_time: str = Field(default="", pattern=r"^$|^\d{2}:\d{2}$")
    end_time: str = Field(default="", pattern=r"^$|^\d{2}:\d{2}$")
    venue: str = ""
    speaker: str = ""
    description: str = ""
    contact: str = ""
    source_url: str = "curated"
    last_checked: Date
    placeholder: bool = False


_events = TypeAdapter(list[Event])

SCHEMA = """
DROP TABLE IF EXISTS events;
DROP TABLE IF EXISTS locality;
CREATE TABLE events (id TEXT PRIMARY KEY, title TEXT, date TEXT, start_time TEXT, end_time TEXT, venue TEXT,
  speaker TEXT, description TEXT, contact TEXT, source_url TEXT, last_checked TEXT, placeholder INTEGER);
CREATE TABLE locality (id TEXT PRIMARY KEY, type TEXT, name TEXT, veg_options INTEGER, body TEXT,
  last_checked TEXT, placeholder INTEGER);
"""


def load_events(path: Path | None = None) -> list[Event]:
    path = path or settings.schedule_path
    if not path.exists():
        return []
    return _events.validate_python(json.loads(path.read_text(encoding="utf-8")))


class ScheduleStore:
    """In-memory SQLite rebuilt from the curated JSON files at startup, so edits need only a restart."""

    def __init__(self, schedule_path: Path | None = None, locality_path: Path | None = None) -> None:
        self._db = sqlite3.connect(":memory:", check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self.events = load_events(schedule_path)
        self.places = locality.load(locality_path) if (locality_path or settings.locality_path).exists() else []
        with self._lock:
            self._db.executescript(SCHEMA)
            self._db.executemany("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [
                (e.id, e.title, e.date.isoformat(), e.start_time, e.end_time, e.venue, e.speaker, e.description,
                 e.contact, e.source_url, e.last_checked.isoformat(), int(e.placeholder)) for e in self.events])
            self._db.executemany("INSERT INTO locality VALUES (?,?,?,?,?,?,?)", [
                (p.id, p.type, p.name, None if getattr(p, "veg_options", None) is None else int(p.veg_options),
                 p.model_dump_json(),
                 p.last_checked.isoformat(), int(p.placeholder)) for p in self.places])
            self._db.commit()
        real_events = sum(not e.placeholder for e in self.events)
        real_places = sum(not p.placeholder for p in self.places)
        self.status_detail = f"events={real_events} real, locality={real_places} real"

    def schedule(self, on: str | None = None, venue: str | None = None, limit: int = 20) -> list[dict]:
        sql, args = "SELECT * FROM events WHERE placeholder=0", []
        if on:
            sql += " AND date=?"
            args.append(on)
        if venue:
            sql += " AND lower(venue) LIKE ?"
            args.append(f"%{venue.lower()}%")
        sql += " ORDER BY date, start_time LIMIT ?"
        args.append(limit)
        with self._lock:
            return [{k: r[k] for k in r.keys() if k != "placeholder"} for r in self._db.execute(sql, args)]

    def upcoming(self, today: str | None = None, limit: int = 3) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM events WHERE placeholder=0 AND date>=? ORDER BY date, start_time "
                                    "LIMIT ?", (today or Date.today().isoformat(), limit))
            return [{k: r[k] for k in r.keys() if k != "placeholder"} for r in rows]

    def local(self, kind: str, veg: bool | None = None, limit: int | None = 8, unconfirmed_veg: bool = False) -> list[dict]:
        sql, args = "SELECT body FROM locality WHERE placeholder=0 AND type=?", [kind]
        if unconfirmed_veg:
            sql += " AND veg_options IS NULL"
        elif veg is not None:
            sql += " AND veg_options=?"
            args.append(int(veg))
        sql += " ORDER BY name"
        if limit is not None:
            sql += " LIMIT ?"
            args.append(limit)
        with self._lock:
            return [json.loads(r["body"]) for r in self._db.execute(sql, args)]

    def close(self) -> None:
        with self._lock:
            self._db.close()


if __name__ == "__main__":
    try:
        events = load_events()
    except (ValidationError, json.JSONDecodeError) as exc:
        print(f"schedule.json: INVALID\n{exc}")
        sys.exit(1)
    real = [e for e in events if not e.placeholder]
    print(f"{len(events)} events, {len(real)} real, {len(events) - len(real)} placeholders")
    print("schedule.json: VALID")
