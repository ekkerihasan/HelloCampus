"""Chroma + BM25 hybrid store (ADDENDUM-01 section 7): heading-aware chunking, content-hash embedding cache,
idempotent ingest, vector and keyword search fused with reciprocal rank fusion, refusal gate, citations."""
import asyncio
import logging
import re
import time
from collections import OrderedDict
from datetime import date
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings
from pydantic import BaseModel, Field

from backend.config import settings
from backend.rag.bm25 import BM25
from backend.rag.embed_cache import EmbedCache, content_hash
from scraper.normalize import Record
from scraper.scrape_github import optin_usernames

log = logging.getLogger("hello_campus.rag")

COLLECTIONS = ("campus", "achievements", "students", "locality")
WORDS_PER_TOKEN = 0.75
HEADING = re.compile(r"^\s*(#{1,6}\s+.+|[A-Z][^\n.!?]{2,80})\s*$")


class Hit(BaseModel):
    text: str
    title: str
    source_url: str
    collection: str
    score: float = 0.0  # vector cosine similarity (0 when only BM25 found it)
    keyword_coverage: float = 0.0
    rrf: float = 0.0
    entity_id: str = ""
    last_checked: str = ""
    record_id: str = ""
    chunk_id: str = ""
    sources: str = ""  # derived records: newline-separated "url\ttitle" of the real pages they list (M-015)


class Source(BaseModel):
    title: str
    url: str  # "curated" for hand-entered locality data
    collection: str
    last_checked: str = ""
    citations: list[int] = Field(default_factory=list)


class IngestStats(BaseModel):
    chunks: int = 0
    embedded: int = 0
    cached: int = 0
    removed: int = 0


def chunk_words(text: str, tokens: int | None = None, overlap: int | None = None) -> list[str]:
    size = max(1, int((settings.chunk_tokens if tokens is None else tokens) * WORDS_PER_TOKEN))
    step = size - int((settings.chunk_overlap_tokens if overlap is None else overlap) * WORDS_PER_TOKEN)
    if step <= 0:
        raise ValueError("Chunk overlap must be smaller than chunk size")
    words = text.split()
    if len(words) <= size:
        return [" ".join(words)] if words else []
    return [" ".join(words[i:i + size]) for i in range(0, max(len(words) - size + step, 1), step)]


def chunk_prose(text: str) -> list[str]:
    """Split on headings first, merge small sections, then window long sections with overlap."""
    sections: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if HEADING.match(line) and current and len(" ".join(current).split()) > 40:
            sections.append("\n".join(current))
            current = []
        if line.strip():
            current.append(line.strip())
    if current:
        sections.append("\n".join(current))
    size = int(settings.chunk_tokens * WORDS_PER_TOKEN)
    merged: list[str] = []
    for sec in sections:
        if merged and len(merged[-1].split()) + len(sec.split()) <= size:
            merged[-1] = f"{merged[-1]}\n{sec}"
        else:
            merged.append(sec)
    return [c for sec in merged for c in chunk_words(sec)]


def _valid(meta: dict) -> bool:
    until = meta.get("valid_until") or ""
    return not until or until >= date.today().isoformat()


class VectorStore:
    def __init__(self, embedder, path: Path | None = None, cache_path: Path | None = None) -> None:
        self.embedder = embedder
        self.client = chromadb.PersistentClient(path=str(path or settings.chroma_dir),
                                               settings=ChromaSettings(anonymized_telemetry=False))
        self.cache = EmbedCache(cache_path)
        model = getattr(embedder, "embed_model", "")
        self.cols = {}
        for name in COLLECTIONS:
            col = self.client.get_or_create_collection(name, embedding_function=None,
                                                      metadata={"hnsw:space": "cosine", "embed_model": model})
            if model and (col.metadata or {}).get("embed_model") not in (model, None):
                log.warning("collection %s was embedded with %s, recreating for %s", name,
                            (col.metadata or {}).get("embed_model"), model)
                self.client.delete_collection(name)
                col = self.client.create_collection(name, embedding_function=None,
                                                    metadata={"hnsw:space": "cosine", "embed_model": model})
            self.cols[name] = col
        self._query_vectors: OrderedDict[str, asyncio.Task] = OrderedDict()  # LRU of query embeddings (M-008)
        self.bm25: dict[str, BM25] = {}
        self._metas: dict[str, dict[str, tuple[str, dict]]] = {}
        for name in COLLECTIONS:
            self._rebuild_bm25(name)

    @property
    def status_detail(self) -> str:
        return " ".join(f"{n}={c.count()}" for n, c in self.cols.items())

    def _rebuild_bm25(self, name: str) -> None:
        data = self.cols[name].get(include=["documents", "metadatas"])
        ids, docs, metas = data["ids"], data["documents"] or [], data["metadatas"] or []
        self.bm25[name] = BM25(ids, docs)
        self._metas[name] = {i: (d, m or {}) for i, d, m in zip(ids, docs, metas)}

    def warm_up(self) -> None:
        """Load each HNSW index from disk at startup with a stored vector, so the first visitor does not pay for it.
        Local only: no embedding call, no quota."""
        for name, col in self.cols.items():
            try:
                sample = col.peek(1)
                vectors = sample.get("embeddings")
                if vectors is not None and len(vectors):
                    col.query(query_embeddings=[list(vectors[0])], n_results=1)
            except Exception:  # noqa: BLE001, warm-up is an optimisation
                log.warning("warm-up query failed on %s", name, exc_info=True)

    def prefetch(self, text: str) -> None:
        """Start embedding a query now, e.g. while the chat model is still picking a tool (M-008)."""
        key = text.strip()
        if not key:
            return
        if key in self._query_vectors:
            self._query_vectors.move_to_end(key)
            return
        self._query_vectors[key] = asyncio.ensure_future(self.embedder.embed_query(key))
        while len(self._query_vectors) > settings.query_embed_cache:
            self._query_vectors.popitem(last=False)

    async def query_vector(self, text: str) -> list[float]:
        self.prefetch(text)
        task = self._query_vectors[text.strip()]
        try:
            return await asyncio.shield(task)
        except Exception:
            self._query_vectors.pop(text.strip(), None)  # never cache a failure
            raise

    async def aclose(self) -> None:
        await asyncio.to_thread(self.cache.close)
        if hasattr(self.embedder, "aclose"):
            await self.embedder.aclose()

    async def ingest(self, collection: str, records: list[Record], whole: bool = False) -> IngestStats:
        """chunk -> hash -> embed new or changed only -> upsert -> delete stale -> rebuild BM25."""
        model = getattr(self.embedder, "embed_model", "")
        ids, docs, metas, titles, hashes = [], [], [], [], []
        for r in records:
            chunks = [r.text] if whole else chunk_prose(r.text)
            for i, chunk in enumerate(chunks):
                doc = f"{r.title}\n{chunk}"  # title prefix keeps short chunks in context (7.3)
                h = content_hash(model, doc)
                ids.append(f"{r.id}#{i}")
                docs.append(doc)
                titles.append(r.title)
                hashes.append(h)
                metas.append({"collection": collection, "title": r.title, "source_url": r.source_url,
                              "last_checked": r.last_checked, "entity_id": r.entity_id, "record_id": r.id,
                              "content_hash": h, "valid_until": str(r.extra.get("valid_until", "")),
                              "sources": "\n".join(f"{u}\t{t}" for u, t in r.extra.get("sources", []))})
        stats = IngestStats(chunks=len(ids))
        cached = await asyncio.to_thread(self.cache.get_many, hashes)
        todo = [i for i, h in enumerate(hashes) if h not in cached]
        if todo:
            vectors = await self.embedder.embed([docs[i] for i in todo], titles=[titles[i] for i in todo])
            fresh = {hashes[i]: v for i, v in zip(todo, vectors)}
            await asyncio.to_thread(self.cache.put_many, model, fresh)
            cached.update(fresh)
        stats.embedded, stats.cached = len(todo), len(ids) - len(todo)
        col = self.cols[collection]
        existing = await asyncio.to_thread(col.get, include=[])
        stale = set(existing["ids"]) - set(ids)
        if ids:
            await asyncio.to_thread(col.upsert, ids=ids, documents=docs, metadatas=metas,
                                    embeddings=[cached[h] for h in hashes])
        if stale:
            await asyncio.to_thread(col.delete, ids=list(stale))
        stats.removed = len(stale)
        await asyncio.to_thread(self._rebuild_bm25, collection)
        log.info("ingested %s: %s", collection, stats.model_dump())
        return stats

    async def retrieve(self, question: str, collections: list[str], k: int | None = None,
                       keyword_query: str | None = None) -> list[Hit]:
        """Vector top 10 and BM25 top 10 per collection, merged with RRF, top k. `keyword_query` lets the
        caller pass an English translation for BM25 while the vector side uses the original question."""
        start = time.perf_counter()
        k = k or settings.rag_top_k_chat
        cols = [c for c in collections if c in self.cols]
        qvec = await self.query_vector(question)
        allowed = await asyncio.to_thread(optin_usernames) if "students" in cols else set()

        def _search() -> list[Hit]:
            fused: dict[str, Hit] = {}
            for name in cols:
                col = self.cols[name]
                n = col.count()
                if n == 0 or (name == "students" and not allowed):
                    continue
                where = {"entity_id": {"$in": sorted(allowed)}} if name == "students" else None
                ranked: list[tuple[str, str, dict, float, float]] = []
                try:
                    res = col.query(query_embeddings=[qvec], n_results=min(settings.rag_vector_k, n), where=where)
                except Exception:  # noqa: BLE001, Chroma's HNSW reader can race a fresh write; keep BM25 results
                    log.warning("vector query failed on %s, using keyword results only", name, exc_info=True)
                    res = {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
                for cid, doc, meta, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0],
                                                res["distances"][0]):
                    ranked.append((cid, doc, meta or {}, round(1 - dist, 4), 0.0))
                vec_rank = {cid: i for i, (cid, *_rest) in enumerate(ranked)}
                bm = self.bm25[name].search(keyword_query or question, settings.rag_bm25_k)
                bm_rank = {cid: i for i, (cid, _s, _c) in enumerate(bm)}
                coverage = {cid: cov for cid, _s, cov in bm}
                for cid in set(vec_rank) | set(bm_rank):
                    doc, meta = self._metas[name].get(cid, ("", {}))
                    vrow = next((r for r in ranked if r[0] == cid), None)
                    if vrow:
                        doc, meta = vrow[1], vrow[2]
                    if not doc or not _valid(meta):
                        continue
                    if name == "students" and meta.get("entity_id", "").lower() not in allowed:
                        continue
                    rrf = sum(1 / (settings.rag_rrf_k + r + 1) for r in
                              (vec_rank.get(cid), bm_rank.get(cid)) if r is not None)
                    fused[cid] = Hit(text=doc, score=vrow[3] if vrow else 0.0, keyword_coverage=round(
                        coverage.get(cid, 0.0), 4), rrf=round(rrf, 6), chunk_id=cid, **{
                        f: meta.get(f, "") for f in ("title", "source_url", "collection", "entity_id",
                                                     "last_checked", "record_id", "sources")})
            return sorted(fused.values(), key=lambda h: -h.rrf)[:k]

        hits = await asyncio.to_thread(_search)
        log.info("retrieve %d ms, top=%s, cols=%s", (time.perf_counter() - start) * 1000,
                 f"{hits[0].score:.3f}/{hits[0].keyword_coverage:.2f}" if hits else "none", cols)
        return hits


def is_confident(h: Hit) -> bool:
    return h.score >= settings.rag_min_score or h.keyword_coverage >= settings.rag_min_keyword_coverage


def confident(hits: list[Hit]) -> list[Hit]:
    """Hits that pass the refusal gate: semantic match above RAG_MIN_SCORE or a strong exact keyword match.
    Empty means the host must say it does not know yet."""
    return [h for h in hits if is_confident(h)]


def sources_for(hits: list[Hit], indices: set[int] | None = None) -> list[Source]:
    seen: dict[str, Source] = {}
    for index, h in enumerate(hits, 1):
        if indices is not None and index not in indices:
            continue
        if h.source_url.startswith("derived:"):
            # A derived list cites the real pages it was built from, one chip each; it has no URL of its own.
            for line in h.sources.splitlines():
                url, _, title = line.partition("\t")
                if url:
                    seen.setdefault(url, Source(title=title or url, url=url, collection=h.collection,
                                                last_checked=h.last_checked)).citations.append(index)
            continue
        key = h.source_url if h.source_url != "curated" else f"curated:{h.title}"
        if key not in seen:
            seen[key] = Source(title=h.title, url=h.source_url, collection=h.collection, last_checked=h.last_checked)
        seen[key].citations.append(index)
    return list(seen.values())
