"""Append-only log of every external call: provider, model, op, status, latency, tokens (ADDENDUM-01 section 8).
Never records keys, prompts or audio."""
import json
import threading
import time
from collections import Counter
from pathlib import Path

from pydantic import BaseModel

from backend.config import settings

_lock = threading.Lock()


class UsageEntry(BaseModel):
    ts: float
    provider: str
    model: str
    op: str
    status: str  # ok | http_<code> | error:<type>
    latency_ms: int
    key_index: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


def record(provider: str, model: str, op: str, status: str, latency_ms: int, key_index: int = 0,
           prompt_tokens: int | None = None, completion_tokens: int | None = None,
           path: Path | None = None) -> None:
    entry = UsageEntry(ts=time.time(), provider=provider, model=model, op=op, status=status,
                       latency_ms=latency_ms, key_index=key_index, prompt_tokens=prompt_tokens,
                       completion_tokens=completion_tokens)
    target = path or settings.usage_log_path
    try:
        with _lock:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as f:
                f.write(entry.model_dump_json() + "\n")
    except OSError:
        pass  # logging must never break a visitor request


def summary(path: Path | None = None, since: float = 0.0) -> dict:
    """Counts per provider/model/status and token totals, for /debug and PROGRESS.md."""
    target = path or settings.usage_log_path
    calls: Counter = Counter()
    statuses: Counter = Counter()
    tokens: Counter = Counter()
    if target.exists():
        for line in target.read_text(encoding="utf-8").splitlines():
            try:
                e = UsageEntry(**json.loads(line))
            except (ValueError, TypeError):
                continue
            if e.ts < since:
                continue
            key = f"{e.provider}/{e.model}/{e.op}"
            calls[key] += 1
            statuses[f"{key}/{e.status}"] += 1
            tokens[key] += (e.prompt_tokens or 0) + (e.completion_tokens or 0)
    return {"calls": dict(calls), "statuses": dict(statuses), "tokens": dict(tokens),
            "rate_limited": sum(v for k, v in statuses.items() if k.endswith("/http_429"))}
