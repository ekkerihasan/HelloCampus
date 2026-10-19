"""One chat turn: route, retrieve, refuse or generate, cite, remember."""
import asyncio
import logging
import re
import time
from typing import AsyncIterator

from pydantic import BaseModel

from backend.llm.characters import CharacterName, character
from backend.llm.client import OllamaClient
from backend.llm.prompts import REFUSAL, build_messages, is_smalltalk
from backend.memory.extract import extract_and_save
from backend.memory.store import MemoryStore, visitor_block
from backend.rag.router import route
from backend.rag.store import Hit, Source, VectorStore, confident, sources_for

log = logging.getLogger("hello_campus.chat")
_background: set[asyncio.Task] = set()


class ChatRequest(BaseModel):
    message: str
    character: CharacterName = CharacterName.guide
    visitor_id: str | None = None


class ChatEvent(BaseModel):
    event: str  # meta | token | sources | done | error
    data: dict


def cited_sources(answer: str, hits: list[Hit]) -> list[Source]:
    """Sources the answer actually cites with [n]; all context sources if it cites none."""
    nums = {int(n) for n in re.findall(r"\[(\d+)\]", answer)}
    used = [h for i, h in enumerate(hits, 1) if i in nums]
    return sources_for(used or hits)


async def run_turn(req: ChatRequest, llm: OllamaClient, store: VectorStore | None,
                   mem: MemoryStore | None) -> AsyncIterator[ChatEvent]:
    start = time.perf_counter()
    char = character(req.character)
    visitor = mem.get(req.visitor_id) if (mem and req.visitor_id) else None
    history = mem.history(visitor.id) if (mem and visitor) else []
    smalltalk = is_smalltalk(req.message)

    hits: list[Hit] = []
    cols: list[str] = []
    if not smalltalk:
        if store is None:
            yield ChatEvent(event="error", data={"message": "Knowledge base is not loaded, so I can't look things up right now."})
            return
        cols = await route(req.message, llm)
        hits = confident(await store.retrieve(req.message, cols))
    yield ChatEvent(event="meta", data={"character": char.name.value, "temperature": char.temperature,
                                        "collections": cols, "smalltalk": smalltalk})

    if not smalltalk and not hits:
        answer = REFUSAL
        yield ChatEvent(event="token", data={"t": answer})
        yield ChatEvent(event="sources", data={"sources": [], "refused": True})
    else:
        msgs = build_messages(char, req.message, hits, visitor_block(visitor), history, smalltalk)
        parts: list[str] = []
        async for tok in llm.stream_chat(msgs, temperature=char.temperature):
            parts.append(tok)
            yield ChatEvent(event="token", data={"t": tok})
        answer = "".join(parts)
        srcs = [] if smalltalk else cited_sources(answer, hits)
        yield ChatEvent(event="sources", data={"sources": [s.model_dump() for s in srcs], "refused": False})

    if mem and visitor:
        mem.add_turn(visitor.id, "user", req.message)
        mem.add_turn(visitor.id, "assistant", answer)
        task = asyncio.create_task(extract_and_save(llm, mem, visitor, req.message, answer))
        _background.add(task)
        task.add_done_callback(_background.discard)
    yield ChatEvent(event="done", data={"ms": int((time.perf_counter() - start) * 1000)})
