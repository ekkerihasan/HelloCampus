"""T0.1/T0.2 provider layer: retry with backoff, 429 key rotation, failover, usage log, parsing. No real calls."""
import base64
import json

import httpx
import pytest

from backend.config import settings
from backend.llm.client import ChatMessage, OpenAICompatClient, TextLLM
from backend.llm.gemini import GeminiClient
from backend.providers import usage
from backend.providers.retry import ProviderError

HI = [ChatMessage(role="user", content="hi")]


def client(handler, provider="groq", keys=("k1", "k2")) -> OpenAICompatClient:
    return OpenAICompatClient(provider, "https://fake.test/v1", list(keys), "chat-model", "fast-model",
                              "stt-model", transport=httpx.MockTransport(handler))


def ok_chat(content="hello", tool_calls=None):
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return httpx.Response(200, json={"choices": [{"message": msg}],
                                     "usage": {"prompt_tokens": 5, "completion_tokens": 2}})


def sse(*tokens: str) -> str:
    body = "".join("data: " + json.dumps({"choices": [{"delta": {"content": t}}]}) + "\n\n" for t in tokens)
    return body + "data: [DONE]\n\n"


async def test_429_rotates_key_then_succeeds():
    seen = []

    def handler(req):
        seen.append(req.headers["authorization"])
        return httpx.Response(429, headers={"retry-after": "0"}) if len(seen) == 1 else ok_chat()

    c = client(handler)
    out = await c.complete(HI, 0.2)
    assert out.content == "hello"
    assert seen == ["Bearer k1", "Bearer k2"]
    assert usage.summary()["rate_limited"] == 1
    assert "k1" not in settings.usage_log_path.read_text()  # keys never logged
    await c.aclose()


async def test_non_retryable_error_fails_fast():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(400, json={"error": "bad"})

    c = client(handler)
    with pytest.raises(ProviderError) as exc:
        await c.complete(HI, 0.2)
    assert exc.value.status == 400 and len(calls) == 1
    await c.aclose()


async def test_retries_are_bounded_on_server_errors():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(503)

    c = client(handler)
    with pytest.raises(ProviderError):
        await c.complete(HI, 0.2)
    assert len(calls) == settings.retry_attempts
    await c.aclose()


async def test_tool_calls_parsed_and_provider_extra_echoed():
    bodies = []
    call = {"id": "c1", "type": "function",
            "function": {"name": "get_schedule", "arguments": '{"date": "2026-10-20"}'},
            "extra_content": {"google": {"thought_signature": "sig"}}}

    def handler(req):
        bodies.append(json.loads(req.content))
        return ok_chat("", [call]) if len(bodies) == 1 else ok_chat("done")

    c = client(handler, "gemini", ["g"])
    msg = await c.complete(HI, 0.0, tools=[{"type": "function"}], tool_choice="required")
    assert msg.tool_calls[0].name == "get_schedule" and msg.tool_calls[0].arguments == {"date": "2026-10-20"}
    await c.complete([*HI, msg, ChatMessage(role="tool", tool_call_id="c1", content="{}")], 0.2)
    echoed = bodies[1]["messages"][1]["tool_calls"][0]
    assert echoed["extra_content"] == {"google": {"thought_signature": "sig"}}
    assert bodies[0]["tool_choice"] == "required"
    await c.aclose()


async def test_stream_yields_tokens():
    c = client(lambda req: httpx.Response(200, text=sse("Hel", "lo")))
    assert [t async for t in c.stream_chat(HI, 0.8)] == ["Hel", "lo"]
    await c.aclose()


async def test_json_mode_and_invalid_json():
    replies = iter(['{"ok": true}', "not json"])
    bodies = []

    def handler(req):
        bodies.append(json.loads(req.content))
        return ok_chat(next(replies))

    c = client(handler)
    assert await c.chat_json([ChatMessage(role="user", content="Return JSON")]) == {"ok": True}
    assert await c.chat_json([ChatMessage(role="user", content="Return JSON")]) == {}
    assert bodies[0]["model"] == "fast-model" and bodies[0]["response_format"] == {"type": "json_object"}
    await c.aclose()


async def test_text_llm_fails_over_when_groq_blocked():
    llm = TextLLM([client(lambda req: httpx.Response(404, json={"error": {"message": "Not Found"}})),
                   client(lambda req: ok_chat("from gemini"), "gemini", ["g"])])
    assert await llm.chat(HI, 0.2) == "from gemini"
    assert llm.active == "gemini"
    llm2 = TextLLM([client(lambda req: httpx.Response(404)),
                    client(lambda req: httpx.Response(200, text=sse("x")), "gemini", ["g"])])
    assert [t async for t in llm2.stream_chat(HI, 0.2)] == ["x"]
    await llm.aclose()
    await llm2.aclose()


async def test_failed_backend_is_skipped_during_cooldown():
    groq_calls = []

    def groq(req):
        groq_calls.append(1)
        return httpx.Response(404)

    llm = TextLLM([client(groq), client(lambda req: ok_chat("g"), "gemini", ["g"])])
    await llm.chat(HI, 0.2)
    await llm.chat(HI, 0.2)
    assert len(groq_calls) == 1  # one fast failure, then skipped, saving latency and quota
    await llm.aclose()


async def test_missing_model_id_fails_loudly():
    c = OpenAICompatClient("groq", "https://fake.test/v1", ["k"], "", "",
                           transport=httpx.MockTransport(lambda req: ok_chat()))
    with pytest.raises(ProviderError, match="not set"):
        await c.complete(HI, 0.2)
    await c.aclose()


async def test_gemini_embed_uses_prefix_templates_and_dimensions(monkeypatch):
    monkeypatch.setattr(settings, "gemini_embed_model", "gemini-embedding-2")
    bodies = []

    def handler(req):
        body = json.loads(req.content)
        bodies.append((req.url.path, body))
        return httpx.Response(200, json={"embeddings": [{"values": [0.1, 0.2]} for _ in body["requests"]]})

    g = GeminiClient("key", transport=httpx.MockTransport(handler))
    assert await g.embed(["doc text"], titles=["Library"]) == [[0.1, 0.2]]
    assert await g.embed_query("when open") == [0.1, 0.2]
    doc, query = bodies[0][1]["requests"][0], bodies[1][1]["requests"][0]
    assert bodies[0][0].endswith("gemini-embedding-2:batchEmbedContents")
    assert "taskType" not in doc and doc["content"]["parts"][0]["text"] == "title: Library | text: doc text"
    assert query["content"]["parts"][0]["text"] == "task: search result | query: when open"
    assert doc["outputDimensionality"] == settings.embed_dimensions
    await g.aclose()


async def test_live_token_v1beta_with_constraints(monkeypatch):
    monkeypatch.setattr(settings, "gemini_live_model", "live-model")
    seen = []

    def handler(req):
        seen.append((req.url.path, json.loads(req.content), req.headers.get("x-goog-api-key")))
        return httpx.Response(200, json={"name": "auth_tokens/abc"})

    g = GeminiClient("secret", transport=httpx.MockTransport(handler))
    out = await g.mint_live_token({"responseModalities": ["AUDIO"], "temperature": 0.2, "tools": [],
                                   "systemInstruction": {"parts": [{"text": "x"}]}, "sessionResumption": {}})
    path, body, key = seen[0]
    assert path == "/v1beta/auth_tokens" and key == "secret"
    setup = body["bidiGenerateContentSetup"]
    assert body["uses"] == 1 and setup["model"] == "models/live-model" and "liveConnectConstraints" not in body
    assert setup["generationConfig"] == {"responseModalities": ["AUDIO"], "temperature": 0.2}
    assert "systemInstruction" in setup and "tools" in setup
    assert "sessionResumption" not in setup and "sessionResumption" not in body["fieldMask"]
    assert set(body["fieldMask"].split(",")) == {"model", "systemInstruction", "tools",
                                                 "generationConfig.responseModalities", "generationConfig.temperature"}
    assert out["token"] == "auth_tokens/abc" and "secret" not in json.dumps(out)
    await g.aclose()


async def test_gemini_tts_wraps_pcm_as_wav(monkeypatch):
    monkeypatch.setattr(settings, "gemini_tts_model", "tts-model")
    pcm = b"\x00\x01" * 100
    reply = {"candidates": [{"content": {"parts": [
        {"inlineData": {"mimeType": "audio/L16", "data": base64.b64encode(pcm).decode()}}]}}]}
    g = GeminiClient("k", transport=httpx.MockTransport(lambda req: httpx.Response(200, json=reply)))
    wav = await g.speak("hi")
    assert wav[:4] == b"RIFF" and wav.endswith(pcm)
    await g.aclose()


async def test_real_network_is_blocked_in_tests():
    async with httpx.AsyncClient() as c:
        with pytest.raises(RuntimeError, match="blocked"):
            await c.get("https://example.org")


async def test_reasoning_effort_sent_only_when_configured():
    bodies = []

    def handler(req):
        bodies.append(json.loads(req.content))
        return ok_chat()

    plain = client(handler)
    tuned = OpenAICompatClient("gemini", "https://fake.test/v1", ["g"], "chat-model", "fast-model",
                               reasoning_effort="low", transport=httpx.MockTransport(handler))
    await plain.complete(HI, 0.2)
    await tuned.complete(HI, 0.2)
    assert "reasoning_effort" not in bodies[0] and bodies[1]["reasoning_effort"] == "low"
    await plain.aclose()
    await tuned.aclose()


async def test_timeouts_retried_once_then_fail_over():
    calls = []

    def slow(req):
        calls.append(1)
        raise httpx.ReadTimeout("slow model", request=req)

    llm = TextLLM([client(slow, "gemini", ["g"]), client(lambda req: ok_chat("fast"), "groq", ["k"])])
    assert await llm.chat(HI, 0.2) == "fast"
    assert len(calls) == settings.retry_timeouts + 1  # not retry_attempts times 30 s
    await llm.aclose()


async def test_stream_without_first_token_in_time_fails_over(monkeypatch):
    import asyncio
    monkeypatch.setattr(settings, "text_first_token_timeout_s", 0.05)

    class Stalled:
        provider, model, fast_model = "slow", "m", "f"
        ring = type("R", (), {"keys": ["k"]})()

        async def stream_chat(self, messages, temperature):
            await asyncio.sleep(5)
            yield "never"

        async def aclose(self):
            pass

    llm = TextLLM([Stalled(), client(lambda req: httpx.Response(200, text=sse("ok")), "gemini", ["g"])])
    assert [t async for t in llm.stream_chat(HI, 0.2)] == ["ok"]
    assert llm.active == "gemini"
    await llm.aclose()


async def test_429_with_single_key_fails_over_at_once():
    calls = []

    def busy(req):
        calls.append(1)
        return httpx.Response(429, headers={"retry-after": "0"})

    llm = TextLLM([client(busy, "gemini", ["g"]), client(lambda req: ok_chat("backup"), "gemini-backup", ["g"])])
    assert await llm.chat(HI, 0.2) == "backup"
    assert len(calls) == 1  # no pointless retries against the same exhausted quota (M-011)
    await llm.aclose()


async def test_blocked_provider_cools_down_longer(monkeypatch):
    import time as _time
    llm = TextLLM([client(lambda req: httpx.Response(404)), client(lambda req: ok_chat("g"), "gemini", ["g"])])
    await llm.chat(HI, 0.2)
    assert llm._down_until["groq"] - _time.monotonic() > settings.text_failover_cooldown_s
    await llm.aclose()


async def test_all_busy_waits_then_retries_primary_once(monkeypatch):
    monkeypatch.setattr(settings, "text_busy_retry_s", 0.0)
    replies = iter([httpx.Response(429), ok_chat("second try")])
    primary = client(lambda req: next(replies), "gemini", ["g"])
    backup = client(lambda req: httpx.Response(429), "gemini-backup", ["g"])
    llm = TextLLM([primary, backup])
    assert await llm.chat(HI, 0.2) == "second try"
    await llm.aclose()


async def test_blocked_provider_not_retried_when_others_are_busy(monkeypatch):
    monkeypatch.setattr(settings, "text_busy_retry_s", 0.0)
    groq_calls = []

    def groq(req):
        groq_calls.append(1)
        return httpx.Response(404)

    gem_replies = iter([httpx.Response(429), httpx.Response(429), ok_chat("ok")])
    llm = TextLLM([client(groq), client(lambda req: next(gem_replies), "gemini", ["g"])])
    with pytest.raises(ProviderError):
        await llm.chat(HI, 0.2)  # groq 404, gemini 429, retry gemini 429
    assert await llm.chat(HI, 0.2) == "ok"  # everything cooling down: busy gemini is tried, blocked groq is not
    assert len(groq_calls) == 1
    await llm.aclose()


async def test_embedding_429_waits_and_retries_instead_of_failing():
    """No backup for embeddings, so a 429 on the only key must back off and retry, not fail at once."""
    replies = iter([httpx.Response(429, headers={"retry-after": "0"}),
                    httpx.Response(200, json={"embeddings": [{"values": [0.5]}]})])
    g = GeminiClient("k", transport=httpx.MockTransport(lambda req: next(replies)))
    assert await g.embed_query("library hours") == [0.5]
    await g.aclose()
