"""Registers every startup component with the registry. Imported once by app.py."""
import asyncio

from backend.llm.client import OllamaClient
from backend.memory.store import MemoryStore
from backend.rag.store import VectorStore
from backend.status import registry


async def _load_llm() -> OllamaClient:
    client = await OllamaClient().check()
    return await client.warm_up()


async def _load_rag() -> VectorStore:
    llm = await OllamaClient().check()
    return await asyncio.to_thread(VectorStore, llm)


async def _load_memory() -> MemoryStore:
    return await asyncio.to_thread(MemoryStore)


registry.register("llm", _load_llm)
registry.register("rag", _load_rag)
registry.register("memory", _load_memory)
