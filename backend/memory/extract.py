"""Low-temperature fact extraction after each turn. Returns facts to upsert into visitor memory."""
import logging
import asyncio

from backend.llm.client import ChatMessage, OllamaClient
from backend.memory.store import MemoryStore, Visitor

log = logging.getLogger("hello_campus.memory")

FACT_KEYS = ("preferences", "interests", "plans")
MAX_ITEMS = 8

PROMPT = """You maintain a tiny memory about a campus visitor. Given the current memory and the latest exchange,
return updated memory as JSON with exactly these keys:
{{"preferences": [short strings, e.g. "vegetarian", "budget lunch"],
  "interests": [short strings, e.g. "robotics", "frontend hiring"],
  "plans": [short strings, e.g. "lunch near campus", "attend AI talk"],
  "summary": "one sentence, under 30 words, what the visitor has asked about and decided so far"}}
Only include things the VISITOR said or clearly wants. Keep existing items unless the visitor contradicted them.
Do not include anything said only by the assistant.

Current memory: {memory}
Visitor said: {user}
Assistant replied: {assistant}"""


def _clean_list(v: object) -> list[str]:
    if not isinstance(v, list):
        return []
    out = []
    for item in v:
        s = str(item).strip()
        if s and s.lower() not in (o.lower() for o in out):
            out.append(s[:60])
    return out[:MAX_ITEMS]


async def extract_and_save(llm: OllamaClient, mem: MemoryStore, visitor: Visitor, user: str, assistant: str) -> Visitor:
    memory = {**{k: visitor.facts.get(k, []) for k in FACT_KEYS}, "summary": visitor.summary}
    data = await llm.chat_json([ChatMessage(role="user", content=PROMPT.format(
        memory=memory, user=user, assistant=assistant[:1500]))])
    if not data:
        return visitor
    facts = {**visitor.facts, **{k: _clean_list(data.get(k, visitor.facts.get(k, []))) for k in FACT_KEYS}}
    summary = str(data.get("summary") or visitor.summary)[:300]
    log.info("visitor memory updated")
    return await asyncio.to_thread(mem.update, visitor.id, facts=facts, summary=summary) or visitor
