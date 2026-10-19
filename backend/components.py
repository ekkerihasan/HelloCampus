"""Registers every startup component with the registry. Imported once by app.py."""
import asyncio

from backend.llm.client import OllamaClient
from backend.memory.store import MemoryStore
from backend.rag.store import VectorStore
from backend.speech.stt import SpeechToText
from backend.speech.tts import TextToSpeech
from backend.vision.gesture import GestureDetector
from backend.status import registry


async def _load_llm() -> OllamaClient:
    client = OllamaClient()
    try:
        await client.check()
        return await client.warm_up()
    except BaseException:
        await client.aclose()
        raise


async def _load_rag() -> VectorStore:
    llm = OllamaClient()
    try:
        await llm.check()
        return await asyncio.to_thread(VectorStore, llm)
    except BaseException:
        await llm.aclose()
        raise


async def _load_memory() -> MemoryStore:
    return await asyncio.to_thread(MemoryStore)


registry.register("llm", _load_llm)
registry.register("rag", _load_rag)
registry.register("memory", _load_memory)
registry.register("stt", lambda: asyncio.to_thread(SpeechToText))
registry.register("tts", lambda: asyncio.to_thread(TextToSpeech))
registry.register("gesture", lambda: asyncio.to_thread(GestureDetector))
