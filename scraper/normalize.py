"""Shared record schema, polite HTTP fetching with cache, and JSONL output."""
import hashlib
import json
import logging
import time
import urllib.robotparser
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from backend.config import ROOT, settings

log = logging.getLogger("hello_campus.scraper")
RAW_DIR = ROOT / "data" / "raw"


class Record(BaseModel):
    id: str
    collection: str  # campus | achievements | students | locality
    title: str
    text: str
    source_url: str  # real URL, or "curated" for hand-entered data
    last_checked: str
    entity_id: str = ""  # GitHub username for students
    extra: dict = {}


def record_id(collection: str, key: str) -> str:
    return f"{collection}-{hashlib.sha1(key.encode()).hexdigest()[:12]}"


def today() -> str:
    return date.today().isoformat()


class PoliteFetcher:
    """One request per `scrape_delay_s`, custom User-Agent, robots.txt respected, raw responses cached."""

    def __init__(self, cache_dir: Path = RAW_DIR, delay_s: float | None = None, headers: dict | None = None) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.delay_s = settings.scrape_delay_s if delay_s is None else delay_s
        self.client = httpx.Client(
            headers={"User-Agent": settings.scrape_user_agent, **(headers or {})},
            timeout=20,
            follow_redirects=True,
        )
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._last = 0.0

    def _wait(self) -> None:
        gap = time.monotonic() - self._last
        if gap < self.delay_s:
            time.sleep(self.delay_s - gap)
        self._last = time.monotonic()

    def allowed(self, url: str) -> bool:
        parts = urlparse(url)
        base = f"{parts.scheme}://{parts.netloc}"
        if base not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                self._wait()
                r = self.client.get(f"{base}/robots.txt")
                if r.status_code == 200:
                    rp.parse(r.text.splitlines())
                elif r.status_code in (404, 410):
                    rp.parse([])
                else:
                    rp.parse(["User-agent: *", "Disallow: /"])
            except httpx.HTTPError:
                rp.parse(["User-agent: *", "Disallow: /"])
            self._robots[base] = rp
        return self._robots[base].can_fetch(settings.scrape_user_agent, url)

    def get(self, url: str, check_robots: bool = True, use_cache: bool = True) -> str | None:
        cache = self.cache_dir / (hashlib.sha1(url.encode()).hexdigest() + ".raw")
        if check_robots and not self.allowed(url):
            log.warning("robots.txt disallows %s, skipping", url)
            return None
        if use_cache and cache.exists():
            return cache.read_text(encoding="utf-8")
        self._wait()
        try:
            r = self.client.get(url)
        except httpx.HTTPError as exc:
            log.warning("fetch failed %s: %s", url, exc)
            return None
        if r.status_code != 200:
            log.warning("HTTP %s for %s", r.status_code, url)
            return None
        cache.write_text(r.text, encoding="utf-8")
        return r.text


def write_jsonl(records: list[Record], path: Path) -> None:
    """Writes records sorted by id so re-runs produce stable diffs (ingest is idempotent on id)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    unique = {r.id: r for r in records}
    with path.open("w", encoding="utf-8") as f:
        for rid in sorted(unique):
            f.write(unique[rid].model_dump_json() + "\n")
    log.info("wrote %d records to %s", len(unique), path)


def read_jsonl(path: Path) -> list[Record]:
    if not path.exists():
        return []
    return [Record(**json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
