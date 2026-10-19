"""make rag-eval: hit rate at 4 and refusal accuracy over backend/tests/rag_eval.yaml (ADDENDUM-01 7.6).
Cost: one query embedding per question, plus one fast-model translation per non-English question.
Run: python -m scripts.rag_eval"""
import asyncio
import json
import re
import sys
import time

import httpx
import yaml
from pydantic import BaseModel, Field

from backend.config import settings
from backend.llm.client import build_text_llm
from backend.llm.gemini import GeminiClient
from backend.rag.search import search_campus
from backend.rag.store import VectorStore


class EvalItem(BaseModel):
    q: str
    expect: list[str] = Field(default_factory=list)  # any of these source URLs or entity IDs counts as a hit
    refuse: bool = False
    unknown: bool = False  # in-domain question the data cannot answer: checked through /api/chat
    lang: str = "en"


API = "http://localhost:8000"
ADMITS = re.compile(r"(don't|do not|doesn't|does not) have|not (available|listed|mentioned|in (my|the))|no information|"
                    r"couldn't find|could not find|not sure|help desk|no mention|not mentioned|isn't mentioned", re.I)


async def chat_admits_unknown(question: str) -> tuple[bool, str]:
    """Run the question through the real chat endpoint; pass if it is refused or the answer admits not knowing."""
    answer, refused = "", False
    async with httpx.AsyncClient(timeout=90) as c:
        async with c.stream("POST", f"{API}/api/chat", json={"message": question, "character": "analyst"}) as r:
            event = ""
            async for line in r.aiter_lines():
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    data = json.loads(line[5:])
                    answer += data.get("t", "") if event == "token" else ""
                    refused = refused or (event == "sources" and data.get("refused"))
    return bool(refused or ADMITS.search(answer)), answer.strip()


def load(path=None) -> list[EvalItem]:
    return [EvalItem(**row) for row in yaml.safe_load((path or settings.rag_eval_path).read_text(encoding="utf-8"))]


def is_hit(item: EvalItem, urls: list[str], entities: list[str]) -> bool:
    return any(e in urls or e in entities for e in item.expect)


async def main() -> int:
    items = load()
    store = await asyncio.to_thread(VectorStore, GeminiClient())
    llm = build_text_llm()
    hits = refusals_ok = answerable = must_refuse = unknown_ok = unknowns = 0
    rows = []
    try:
        for item in items:
            start = time.perf_counter()
            if item.unknown:
                unknowns += 1
                ok, answer = await chat_admits_unknown(item.q)
                unknown_ok += ok
                rows.append({"ok": ok, "lang": item.lang, "q": item.q, "refused": False,
                             "ms": int((time.perf_counter() - start) * 1000), "top": "CHAT: " + answer[:110]})
                continue
            r = await search_campus(store, llm, item.q, k=settings.rag_top_k_chat)
            ms = int((time.perf_counter() - start) * 1000)
            urls = [h.source_url for h in r.hits]
            entities = [h.entity_id for h in r.hits if h.entity_id]
            if item.refuse:
                must_refuse += 1
                ok = r.refusal
                refusals_ok += ok
            else:
                answerable += 1
                ok = not r.refusal and is_hit(item, urls, entities)
                hits += ok
            top = r.hits[0] if r.hits else None
            rows.append({"ok": ok, "lang": item.lang, "q": item.q, "ms": ms, "refused": r.refusal,
                         "top": f"{top.score:.3f}/{top.keyword_coverage:.2f} {top.source_url}" if top else ""})
    finally:
        await store.aclose()
        await llm.aclose()
    for row in rows:
        print(f"{'PASS' if row['ok'] else 'FAIL'} [{row['lang']}] {row['ms']:>5} ms  {row['q'][:60]:<60}  "
              f"{'REFUSED' if row['refused'] else row['top']}")
    hit_rate = hits / answerable if answerable else 0.0
    summary = {"hit_rate_at_4": round(hit_rate, 3), "answerable": answerable, "hits": hits,
               "refusals": f"{refusals_ok}/{must_refuse}", "in_domain_unknowns": f"{unknown_ok}/{unknowns}",
               "rag_min_score": settings.rag_min_score,
               "rag_min_keyword_coverage": settings.rag_min_keyword_coverage}
    print(json.dumps(summary))
    return 0 if hit_rate >= 0.8 and refusals_ok == must_refuse and unknown_ok == unknowns else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
