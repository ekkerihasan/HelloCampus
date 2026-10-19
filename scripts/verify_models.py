"""T0.2: one real call per configured model ID. Prints status and latency only, never keys or full outputs.
Run: python -m scripts.verify_models"""
import asyncio
import base64
import time

from backend.config import settings
from backend.llm.client import ChatMessage, build_text_llm
from backend.llm.gemini import QUERY_TASK, GeminiClient

# 1x1 white JPEG, enough to prove the vision path accepts an image.
TINY_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////"
    "////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA=")


async def check(name: str, coro) -> None:
    start = time.perf_counter()
    try:
        detail = await coro
        print(f"PASS {name:<34} {int((time.perf_counter() - start) * 1000):>6} ms  {detail}")
    except Exception as exc:  # noqa: BLE001, report every model
        print(f"FAIL {name:<34} {int((time.perf_counter() - start) * 1000):>6} ms  {str(exc)[:160]}")


async def main() -> None:
    gem = GeminiClient()
    text = build_text_llm()
    hi = [ChatMessage(role="user", content="Reply with the single word: ready")]
    try:
        await check(f"gemini embed doc {settings.gemini_embed_model}",
                    _len(gem.embed(["Hello Campus test document"])))
        await check(f"gemini embed query {settings.gemini_embed_model}", _len(gem.embed(["test query"], QUERY_TASK)))
        await check(f"gemini vision {settings.gemini_vision_model}", gem.generate(
            [{"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(TINY_JPEG).decode()}},
             {"text": "What colour is this image? One word."}], 0.0))
        await check(f"gemini tts {settings.gemini_tts_model}", _bytes(gem.speak("Hello from Hello Campus.")))
        await check(f"gemini live token {settings.gemini_live_model}", _token(gem.mint_live_token()))
        for backend in text.backends:
            await check(f"{backend.provider} chat {backend.model}", backend.chat(hi, 0.2))
            await check(f"{backend.provider} json {backend.fast_model}",
                        backend.chat_json([ChatMessage(role="user", content='Return JSON {"ok": true}')]))
        # Groq TTS is skipped on purpose: Orpheus allows about 100 requests a day (M-005), server TTS is off.
    finally:
        await text.aclose()
        await gem.aclose()


async def _len(coro) -> str:
    vectors = await coro
    return f"dim={len(vectors[0])}"


async def _bytes(coro) -> str:
    return f"{len(await coro)} bytes"


async def _token(coro) -> str:
    t = await coro
    return "token minted" if t.get("token") else "EMPTY token"


if __name__ == "__main__":
    asyncio.run(main())
