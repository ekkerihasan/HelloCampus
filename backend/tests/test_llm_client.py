"""T0.2: client streams tokens at temp 0.2 and 0.8 (needs a running Ollama)."""
import pytest

from backend.config import settings
from backend.llm.client import ChatMessage, OllamaClient

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("temp", [settings.temp_analyst, settings.temp_guide])
async def test_stream_tokens(temp: float) -> None:
    client = await OllamaClient().check()
    msgs = [ChatMessage(role="user", content="Say hello in five words.")]
    tokens = [t async for t in client.stream_chat(msgs, temperature=temp)]
    await client.aclose()
    assert len(tokens) > 1, "expected multiple streamed chunks"
    assert "".join(tokens).strip()


async def test_json_mode() -> None:
    client = await OllamaClient().check()
    msgs = [ChatMessage(role="user", content='Return JSON {"ok": true} and nothing else.')]
    data = await client.chat_json(msgs)
    await client.aclose()
    assert data.get("ok") is True


async def test_embed() -> None:
    client = await OllamaClient().check()
    vecs = await client.embed(["hello campus"])
    await client.aclose()
    assert len(vecs) == 1 and len(vecs[0]) > 100
