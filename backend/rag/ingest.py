"""make ingest: data/clean/*.jsonl and real locality entries -> chunk -> hash -> embed new or changed only ->
Chroma upsert -> BM25 rebuild -> data/ingest_report.json (ADDENDUM-01 7.5). Run: python -m backend.rag.ingest"""
import asyncio
import json
import logging
import re
import time
from pathlib import Path

from backend.config import settings
from backend.llm.gemini import GeminiClient
from backend.rag import locality, posts
from backend.rag.store import IngestStats, VectorStore
from scraper.normalize import Record, read_jsonl
from scraper.scrape_github import optin_usernames

log = logging.getLogger("hello_campus.ingest")


def locality_records(path: Path | None = None) -> list[Record]:
    return [
        Record(id=e.id, collection="locality", title=e.name, text=locality.entry_text(e), source_url=e.source_url,
               last_checked=e.last_checked.isoformat(), extra={"type": e.type})
        for e in locality.load(path) if not e.placeholder
    ]


def student_records(clean_dir: Path, optin_path: Path | None = None) -> list[Record]:
    """Second opt-in gate: even if students.jsonl is stale, only current opt-in usernames get indexed."""
    allowed = optin_usernames(optin_path)
    records = [r for r in read_jsonl(clean_dir / "students.jsonl") if r.entity_id.lower() in allowed]
    for record in records:
        record.entity_id = record.entity_id.lower()
    return records


# Team decisions on conflicting official pages (2026-10-19): /placements/statistics/ is authoritative for placement
# numbers, so the older summary figures on /placements/ are dropped before indexing. data/clean stays as scraped.
CORRECTIONS: dict[str, list[tuple[str, str]]] = {
    "https://aitm.edu.in/": [(r"\s*with our 95% placement record", "")],
    "https://aitm.edu.in/placements/": [(r"Highest Package\s*₹?14\.5 LPA\s*", ""), (r"\|\s*90% Rate\s*-?\s*", "| ")],
}


def apply_corrections(records: list[Record]) -> list[Record]:
    out = []
    for r in records:
        rules = CORRECTIONS.get(r.source_url)
        if rules:
            text, title = r.text, r.title
            for pattern, repl in rules:
                text, title = re.sub(pattern, repl, text), re.sub(pattern, repl, title)
            r = r.model_copy(update={"text": text, "title": title.strip()})
        out.append(r)
    return out


# Lists no single AITM page provides (M-015): built from the scraped pages under these paths, nothing added.
DERIVED_LISTS = {
    "departments": ("https://aitm.edu.in/departments/", "AITM departments and programmes",
                    "AITM has these {n} departments, each with its own official page: {items}."),
    "recruiters": ("https://aitm.edu.in/placements/recruiters/", "Companies that recruit from AITM",
                   "These {n} companies have official AITM recruiter pages: {items}."),
}


def short_title(title: str) -> str:
    for sep in (" | ", " - Recruiter"):
        title = title.split(sep)[0]
    return title.strip()


def derived_records(records: list[Record]) -> list[Record]:
    """One list record per DERIVED_LISTS prefix. Each listed item keeps its own source URL for the chips."""
    out = []
    for key, (prefix, title, template) in DERIVED_LISTS.items():
        pages = sorted((r for r in records if r.source_url.startswith(prefix)), key=lambda r: r.title)
        if len(pages) < 2:
            continue
        names = [short_title(r.title) for r in pages]
        out.append(Record(id=f"campus-derived-{key}", collection="campus", title=title,
                          text=template.format(n=len(pages), items="; ".join(names)),
                          source_url=f"derived:{key}", last_checked=max(r.last_checked for r in pages),
                          extra={"sources": [(r.source_url, short_title(r.title)) for r in pages]}))
    return out


async def ingest_all(store: VectorStore, clean_dir: Path | None = None, locality_path: Path | None = None,
                     optin_path: Path | None = None) -> dict[str, IngestStats]:
    clean_dir = clean_dir or settings.clean_dir
    pasted = posts.post_records()
    # One chunk per achievement, student profile section and locality entry (7.3); campus prose is chunked.
    return {
        "campus": await store.ingest("campus", (campus := apply_corrections(read_jsonl(clean_dir / "campus.jsonl")))
                                     + derived_records(campus) + pasted["campus"]),
        "achievements": await store.ingest("achievements", apply_corrections(read_jsonl(clean_dir / "achievements.jsonl"))
                                           + pasted["achievements"], whole=True),
        "students": await store.ingest("students", student_records(clean_dir, optin_path), whole=True),
        "locality": await store.ingest("locality", locality_records(locality_path), whole=True),
    }


def write_report(stats: dict[str, IngestStats], ms: int, failed: dict[str, str], path: Path | None = None) -> dict:
    report = {"embed_model": settings.gemini_embed_model, "ms": ms,
              "collections": {k: v.model_dump() for k, v in stats.items()}, "failed": failed,
              "totals": {f: sum(getattr(v, f) for v in stats.values()) for f in IngestStats.model_fields}}
    target = path or settings.ingest_report_path
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


async def _main() -> int:
    start = time.perf_counter()
    store = await asyncio.to_thread(VectorStore, GeminiClient())
    failed: dict[str, str] = {}
    try:
        stats = await ingest_all(store)
    except Exception as exc:  # noqa: BLE001, report and exit non-zero
        failed["ingest"] = str(exc)[:300]
        stats = {}
    finally:
        await store.aclose()
    report = write_report(stats, int((time.perf_counter() - start) * 1000), failed)
    print(json.dumps(report, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(asyncio.run(_main()))
