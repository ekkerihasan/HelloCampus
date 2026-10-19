"""Registers every startup component with the registry. Imported once by app.py.
Clients are created once; provider reachability is probed separately so a missing key never blocks startup."""
import asyncio

from backend.llm.client import TextLLM, build_text_llm
from backend.llm.gemini import GeminiClient
from backend.memory.store import MemoryStore
from backend.rag.store import VectorStore
from backend.schedule.store import ScheduleStore
from backend.status import registry
from backend.vision.gesture import GestureDetector


async def _load_text() -> TextLLM:
    return build_text_llm()


async def _load_gemini() -> GeminiClient:
    return GeminiClient()


async def _load_rag() -> VectorStore:
    store = await asyncio.to_thread(VectorStore, GeminiClient())
    await asyncio.to_thread(store.warm_up)
    return store


async def _load_memory() -> MemoryStore:
    return await asyncio.to_thread(MemoryStore)


async def _load_schedule() -> ScheduleStore:
    return await asyncio.to_thread(ScheduleStore)


registry.register("llm", _load_text)
registry.register("gemini", _load_gemini)
registry.register("rag", _load_rag)
registry.register("memory", _load_memory)
registry.register("schedule", _load_schedule)
registry.register("gesture", lambda: asyncio.to_thread(GestureDetector))  # missing model is reported, not fatal
