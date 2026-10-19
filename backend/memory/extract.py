"""Low-temperature fact extraction after each turn. Returns facts to upsert into visitor memory."""
import asyncio
import logging

from backend.config import settings
from backend.llm.client import ChatMessage
from backend.memory.store import MemoryStore, Visitor

log = logging.getLogger("hello_campus.memory")

FACT_KEYS = ("preferences", "interests", "plans")  # "notes" belongs to the remember tool only
MAX_ITEMS = 8

PROMPT = """You maintain a tiny memory about a campus visitor. Given the current memory and the latest exchange,
return updated memory as JSON with exactly these keys:
{{"preferences": [short strings, e.g. "vegetarian", "budget lunch"],
  "interests": [short strings, e.g. "robotics", "frontend hiring"],
  "plans": [short strings, e.g. "lunch near campus", "attend AI talk"],
  "language": "ISO 639-1 code of the language the VISITOR wrote in, e.g. en, hi, kn",
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


async def extract_and_save(llm, mem: MemoryStore, visitor: Visitor, user: str, assistant: str) -> Visitor:
    memory = {**{k: visitor.facts.get(k, []) for k in FACT_KEYS}, "summary": visitor.summary}
    data = await llm.chat_json([ChatMessage(role="user", content=PROMPT.format(
        memory=memory, user=user, assistant=assistant[:1500]))])
    if not data:
        return visitor
    facts = {**visitor.facts, **{k: _clean_list(data.get(k, visitor.facts.get(k, []))) for k in FACT_KEYS}}
    summary = str(data.get("summary") or visitor.summary)[:settings.memory_summary_chars]
    # A misheard two-word fragment must not switch the visitor's language for every later session.
    detected = str(data.get("language") or "").strip().lower()[:8]
    reliable = len(user.split()) >= settings.language_min_words and detected in settings.supported_languages
    language = detected if reliable else visitor.language
    log.info("visitor memory updated")
    return await asyncio.to_thread(mem.update, visitor.id, facts=facts, summary=summary,
                                   language=language) or visitor
