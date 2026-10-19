"""Embeddings cached by content hash in SQLite, so re-ingest never re-embeds unchanged chunks (ADDENDUM-01 7.2)."""
import hashlib
import json
import sqlite3
import threading
from pathlib import Path

from backend.config import settings


def content_hash(model: str, text: str) -> str:
    return hashlib.sha256(f"{model}\n{text}".encode("utf-8")).hexdigest()


class EmbedCache:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path or settings.embed_cache_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._db.execute("CREATE TABLE IF NOT EXISTS embeddings (hash TEXT PRIMARY KEY, model TEXT NOT NULL, "
                             "vector TEXT NOT NULL)")
            self._db.commit()

    def get_many(self, hashes: list[str]) -> dict[str, list[float]]:
        out: dict[str, list[float]] = {}
        with self._lock:
            for i in range(0, len(hashes), 500):
                part = hashes[i:i + 500]
                q = f"SELECT hash, vector FROM embeddings WHERE hash IN ({','.join('?' * len(part))})"
                out.update({h: json.loads(v) for h, v in self._db.execute(q, part)})
        return out

    def put_many(self, model: str, items: dict[str, list[float]]) -> None:
        with self._lock:
            self._db.executemany("INSERT OR REPLACE INTO embeddings (hash, model, vector) VALUES (?,?,?)",
                                 [(h, model, json.dumps(v)) for h, v in items.items()])
            self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()
