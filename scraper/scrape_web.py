"""Scrapes URLs in sources.yaml into data/clean/<collection>.jsonl. Run: python -m scraper.scrape_web"""
import logging
from pathlib import Path

import trafilatura
import yaml

from backend.config import ROOT, settings
from scraper.normalize import PoliteFetcher, Record, record_id, today, write_jsonl

log = logging.getLogger("hello_campus.scraper.web")
SOURCES = ROOT / "scraper" / "sources.yaml"
WEB_COLLECTIONS = ("campus", "achievements")
BLOCKED_HOSTS = ("linkedin.com", "instagram.com")


def extract(html: str, url: str, title_override: str = "") -> tuple[str, str]:
    text = trafilatura.extract(html, url=url, include_comments=False, include_tables=True) or ""
    meta = trafilatura.extract_metadata(html)
    title = title_override or (meta.title if meta and meta.title else url)
    return title.strip(), text.strip()


def scrape(sources_path: Path = SOURCES, out_dir: Path | None = None, fetcher: PoliteFetcher | None = None) -> dict[str, int]:
    out_dir = out_dir or settings.clean_dir
    sources = yaml.safe_load(sources_path.read_text(encoding="utf-8")) or {}
    fetcher = fetcher or PoliteFetcher()
    counts: dict[str, int] = {}
    for collection in WEB_COLLECTIONS:
        records: list[Record] = []
        for entry in sources.get(collection) or []:
            url, title_override = (entry, "") if isinstance(entry, str) else (entry["url"], entry.get("title", ""))
            if any(h in url for h in BLOCKED_HOSTS):
                log.warning("blocked host, skipping %s", url)
                continue
            html = fetcher.get(url)
            if not html:
                continue
            title, text = extract(html, url, title_override)
            if not text:
                log.warning("no article text in %s", url)
                continue
            records.append(Record(id=record_id(collection, url), collection=collection, title=title,
                                  text=text, source_url=url, last_checked=today()))
        if records:
            write_jsonl(records, out_dir / f"{collection}.jsonl")
        counts[collection] = len(records)
        log.info("%s: %d records", collection, len(records))
    return counts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print(scrape())
