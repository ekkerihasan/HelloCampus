"""Embeds data/clean/*.jsonl and real (non-placeholder) locality entries into Chroma.
Run: python -m backend.rag.ingest"""
import asyncio
import logging
from pathlib import Path

from backend.config import settings
from backend.llm.client import OllamaClient
from backend.rag import locality
from backend.rag.store import VectorStore
from scraper.normalize import Record, read_jsonl
from scraper.scrape_github import optin_usernames

log = logging.getLogger("hello_campus.ingest")


def locality_records(path: Path | None = None) -> list[Record]:
    return [
        Record(id=e.id, collection="locality", title=e.name, text=locality.entry_text(e), source_url="curated",
               last_checked=e.last_checked.isoformat(), extra={"type": e.type})
        for e in locality.load(path) if not e.placeholder
    ]


def student_records(clean_dir: Path, optin_path: Path | None = None) -> list[Record]:
    """Second opt-in gate: even if students.jsonl is stale, only current opt-in usernames get indexed."""
    allowed = optin_usernames(optin_path)
    return [r for r in read_jsonl(clean_dir / "students.jsonl") if r.entity_id.lower() in allowed]


async def ingest_all(store: VectorStore, clean_dir: Path | None = None, locality_path: Path | None = None,
                     optin_path: Path | None = None) -> dict[str, int]:
    clean_dir = clean_dir or settings.clean_dir
    counts = {
        "campus": await store.ingest("campus", read_jsonl(clean_dir / "campus.jsonl")),
        "achievements": await store.ingest("achievements", read_jsonl(clean_dir / "achievements.jsonl")),
        "students": await store.ingest("students", student_records(clean_dir, optin_path)),
        "locality": await store.ingest("locality", locality_records(locality_path), whole=True),
    }
    return counts


async def _main() -> None:
    llm = await OllamaClient().check()
    print(await ingest_all(VectorStore(llm)))
    await llm.aclose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    asyncio.run(_main())
