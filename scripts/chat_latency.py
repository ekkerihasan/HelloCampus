"""Measure real local chat first-token latency with the old and bounded context budgets."""
import asyncio
import time

from backend.config import settings
from backend.llm.characters import character
from backend.llm.client import OllamaClient
from backend.llm.prompts import build_messages
from backend.rag.store import VectorStore, confident


async def main():
    llm = await OllamaClient().check()
    store = await asyncio.to_thread(VectorStore, llm)
    question = "How can I contact AITM?"
    hits = confident(await store.retrieve(question, ["campus"]))
    previous_chars, previous_tokens = settings.chat_context_chars, settings.llm_max_output_tokens
    settings.llm_max_output_tokens = 24
    try:
        for label, budget, count in [("previous budget", 6000, 5),
                                      ("bounded budget", previous_chars, settings.chat_context_hits)]:
            settings.chat_context_chars = budget
            messages = build_messages(character("analyst"), question, hits[:count], "", [], False)
            start, first, parts = time.perf_counter(), None, []
            async for token in llm.stream_chat(messages, temperature=settings.temp_analyst):
                if first is None:
                    first = round((time.perf_counter() - start) * 1000)
                parts.append(token)
            print(label, {"prompt_chars": sum(len(m.content) for m in messages), "first_token_ms": first,
                          "total_ms": round((time.perf_counter() - start) * 1000),
                          "partial_reply": "".join(parts)}, flush=True)
    finally:
        settings.chat_context_chars, settings.llm_max_output_tokens = previous_chars, previous_tokens
        await llm.aclose()


if __name__ == "__main__":
    asyncio.run(main())
