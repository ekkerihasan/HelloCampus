"""Chroma vector store: chunking, idempotent ingest, retrieval with similarity scores and citations."""
import asyncio
import logging
import time
from pathlib import Path

import chromadb
from pydantic import BaseModel

from backend.config import settings
from backend.llm.client import OllamaClient
from scraper.normalize import Record

log = logging.getLogger("hello_campus.rag")

COLLECTIONS = ("campus", "achievements", "students", "locality")
DOC_PREFIX = "search_document: "  # nomic-embed-text task prefixes
QUERY_PREFIX = "search_query: "
WORDS_PER_TOKEN = 0.75
EMBED_BATCH = 16


class Hit(BaseModel):
    text: str
    title: str
    source_url: str
    collection: str
    score: float
    entity_id: str = ""
    last_checked: str = ""
    record_id: str = ""


class Source(BaseModel):
    title: str
    url: str  # "curated" for hand-entered locality data
    collection: str
    last_checked: str = ""


def chunk_words(text: str, tokens: int | None = None, overlap: int | None = None) -> list[str]:
    size = int((tokens or settings.chunk_tokens) * WORDS_PER_TOKEN)
    step = size - int((overlap or settings.chunk_overlap_tokens) * WORDS_PER_TOKEN)
    words = text.split()
    if len(words) <= size:
        return [" ".join(words)] if words else []
    return [" ".join(words[i:i + size]) for i in range(0, max(len(words) - size + step, 1), step)]


class VectorStore:
    def __init__(self, llm: OllamaClient, path: Path | None = None) -> None:
        self.llm = llm
        self.client = chromadb.PersistentClient(path=str(path or settings.chroma_dir))
        self.cols = {
            name: self.client.get_or_create_collection(name, metadata={"hnsw:space": "cosine"})
            for name in COLLECTIONS
        }

    @property
    def status_detail(self) -> str:
        return " ".join(f"{n}={c.count()}" for n, c in self.cols.items())

    async def ingest(self, collection: str, records: list[Record], whole: bool = False) -> int:
        """Upserts chunks and deletes chunks no longer present, so re-running is idempotent."""
        ids, docs, metas = [], [], []
        for r in records:
            chunks = [r.text] if whole else chunk_words(r.text)
            for i, chunk in enumerate(chunks):
                ids.append(f"{r.id}#{i}")
                docs.append(f"{r.title}\n{chunk}")
                metas.append({"collection": collection, "title": r.title, "source_url": r.source_url,
                              "last_checked": r.last_checked, "entity_id": r.entity_id, "record_id": r.id})
        col = self.cols[collection]
        stale = set(col.get(include=[])["ids"]) - set(ids)
        if stale:
            col.delete(ids=list(stale))
        for i in range(0, len(ids), EMBED_BATCH):
            batch = docs[i:i + EMBED_BATCH]
            vecs = await self.llm.embed([DOC_PREFIX + d for d in batch])
            col.upsert(ids=ids[i:i + EMBED_BATCH], documents=batch, embeddings=vecs, metadatas=metas[i:i + EMBED_BATCH])
        log.info("ingested %s: %d chunks from %d records, removed %d stale", collection, len(ids), len(records), len(stale))
        return len(ids)

    async def retrieve(self, question: str, collections: list[str], k: int | None = None,
                       where: dict | None = None) -> list[Hit]:
        start = time.perf_counter()
        k = k or settings.rag_top_k
        [qvec] = await self.llm.embed([QUERY_PREFIX + question])

        def _query() -> list[Hit]:
            hits: list[Hit] = []
            for name in collections:
                col = self.cols[name]
                n = col.count()
                if n == 0:
                    continue
                res = col.query(query_embeddings=[qvec], n_results=min(k, n), where=where or None)
                for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
                    hits.append(Hit(text=doc, score=round(1 - dist, 4), **{
                        f: meta.get(f, "") for f in ("title", "source_url", "collection", "entity_id", "last_checked", "record_id")}))
            return sorted(hits, key=lambda h: -h.score)[:k]

        hits = await asyncio.to_thread(_query)
        log.info("retrieve %d ms, best=%.3f, cols=%s", (time.perf_counter() - start) * 1000,
                 hits[0].score if hits else 0, collections)
        return hits


def confident(hits: list[Hit]) -> list[Hit]:
    """Hits at or above RAG_MIN_SCORE. Empty means the app must say it does not know."""
    return [h for h in hits if h.score >= settings.rag_min_score]


def sources_for(hits: list[Hit]) -> list[Source]:
    seen: dict[str, Source] = {}
    for h in hits:
        key = h.source_url if h.source_url != "curated" else f"curated:{h.title}"
        if key not in seen:
            seen[key] = Source(title=h.title, url=h.source_url, collection=h.collection, last_checked=h.last_checked)
    return list(seen.values())
