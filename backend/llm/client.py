"""OpenAI-compatible text client used for Groq (primary) and Gemini's OpenAI endpoint (failover): streamed chat
with per-call temperature, JSON mode, tool calling, Whisper STT and TTS. Every call goes through call_with_retry
for timeout, backoff, key rotation and usage logging. TextLLM fails over between backends (PROGRESS.md)."""
import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator

import httpx
from pydantic import BaseModel, Field

from backend.config import settings
from backend.providers import usage
from backend.providers.retry import KeyRing, ProviderError, call_with_retry, timeout

log = logging.getLogger("hello_campus.llm")


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    extra: dict[str, Any] | None = None  # provider data that must be echoed back (Gemini thought_signature)


class ChatMessage(BaseModel):
    role: str  # system | user | assistant | tool
    content: str = ""
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None

    def wire(self) -> dict:
        out: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            out["tool_calls"] = [{"id": c.id, "type": "function", "function": {
                "name": c.name, "arguments": json.dumps(c.arguments)},
                **({"extra_content": c.extra} if c.extra else {})} for c in self.tool_calls]
        if self.tool_call_id:
            out["tool_call_id"] = self.tool_call_id
        return out


class Transcript(BaseModel):
    text: str
    language: str = ""
    duration_s: float | None = None


def _tokens(response: httpx.Response) -> tuple[int | None, int | None]:
    try:
        u = response.json().get("usage") or {}
    except ValueError:
        return None, None
    return u.get("prompt_tokens"), u.get("completion_tokens")


def parse_tool_calls(raw: list[dict] | None) -> list[ToolCall]:
    calls = []
    for item in raw or []:
        fn = item.get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        calls.append(ToolCall(id=item.get("id", ""), name=fn.get("name", ""),
                              arguments=args if isinstance(args, dict) else {},
                              extra=item.get("extra_content")))
    return calls


class OpenAICompatClient:
    def __init__(self, provider: str, base_url: str, keys: list[str], chat_model: str, fast_model: str,
                 stt_model: str = "", tts_model: str = "", tts_voice: str = "", reasoning_effort: str = "",
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.provider = provider
        self.reasoning_effort = reasoning_effort  # thinking models: lower effort cuts latency (M-008)
        self.ring = KeyRing(provider, [k for k in keys if k])
        self.model, self.fast_model = chat_model, fast_model
        self.stt_model, self.tts_model, self.tts_voice = stt_model, tts_model, tts_voice
        self._http = httpx.AsyncClient(base_url=base_url, timeout=timeout(settings.text_timeout_s),
                                       transport=transport)
        self.status_detail = (f"{provider}: chat={chat_model or 'unset'} fast={fast_model or 'unset'} "
                              f"keys={len(self.ring.keys)}")

    @staticmethod
    def _auth(key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {key}"}

    async def ping(self) -> str:
        """Reachability check without spending tokens: list models."""
        r = await call_with_retry(self.provider, "models", "list_models", self.ring,
                                  lambda k: self._http.get("/models", headers=self._auth(k)))
        ids = {str(m.get("id", "")).removeprefix("models/") for m in r.json().get("data", [])}  # Gemini prefixes IDs
        missing = [m for m in (self.model, self.fast_model, self.stt_model) if m and m not in ids]
        return f"reachable, {len(ids)} models" + (f", MISSING {missing}" if missing else "")

    async def list_models(self) -> list[str]:
        r = await call_with_retry(self.provider, "models", "list_models", self.ring,
                                  lambda k: self._http.get("/models", headers=self._auth(k)))
        return sorted(str(m.get("id", "")).removeprefix("models/") for m in r.json().get("data", []))

    def _body(self, messages: list[ChatMessage], temperature: float, model: str, **extra: Any) -> dict:
        body = {"model": model, "messages": [m.wire() for m in messages], "temperature": temperature,
                "max_tokens": settings.llm_max_output_tokens, **extra}
        if self.reasoning_effort:
            body["reasoning_effort"] = self.reasoning_effort
        return body

    async def complete(self, messages: list[ChatMessage], temperature: float, model: str | None = None,
                       tools: list[dict] | None = None, tool_choice: str = "auto",
                       json_mode: bool = False, max_tokens: int | None = None) -> ChatMessage:
        model = model or self.model
        extra: dict[str, Any] = {}
        if tools:
            extra.update(tools=tools, tool_choice=tool_choice)
        if json_mode:
            extra["response_format"] = {"type": "json_object"}
        if max_tokens:
            extra["max_tokens"] = max_tokens
        body = self._body(messages, temperature, model, **extra)
        r = await call_with_retry(self.provider, model, "tools" if tools else ("json" if json_mode else "chat"),
                                  self.ring, lambda k: self._http.post("/chat/completions", json=body,
                                                                       headers=self._auth(k)), _tokens,
                                  fail_fast_429=True)
        msg = r.json()["choices"][0]["message"]
        return ChatMessage(role="assistant", content=msg.get("content") or "",
                           tool_calls=parse_tool_calls(msg.get("tool_calls")) or None)

    async def stream_chat(self, messages: list[ChatMessage], temperature: float,
                          model: str | None = None) -> AsyncIterator[str]:
        """Yield text tokens as they arrive. Retries happen only before the first byte."""
        model = model or self.model
        body = self._body(messages, temperature, model, stream=True)
        start = time.perf_counter()

        async def send(key: str) -> httpx.Response:
            req = self._http.build_request("POST", "/chat/completions", json=body, headers=self._auth(key))
            resp = await self._http.send(req, stream=True)
            if resp.status_code >= 400:  # read the error body so retry logging can use it, then release
                await resp.aread()
                await resp.aclose()
            return resp

        resp = await call_with_retry(self.provider, model, "stream", self.ring, send, fail_fast_429=True)
        first = True
        try:
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                if chunk.get("error"):
                    raise ProviderError(self.provider, str(chunk["error"])[:200])
                choices = chunk.get("choices") or []
                token = (choices[0].get("delta") or {}).get("content") if choices else None
                if token:
                    if first:
                        ms = int((time.perf_counter() - start) * 1000)
                        log.info("%s first token %d ms (temp %.1f)", self.provider, ms, temperature)
                        usage.record(self.provider, model, "stream_first_token", "ok", ms, self.ring.index)
                        first = False
                    yield token
        finally:
            await resp.aclose()

    async def chat(self, messages: list[ChatMessage], temperature: float, model: str | None = None) -> str:
        return (await self.complete(messages, temperature, model=model)).content

    async def chat_json(self, messages: list[ChatMessage], temperature: float | None = None,
                        model: str | None = None) -> dict:
        """JSON-mode call on the fast model. Returns {} if the model emits invalid JSON."""
        temp = settings.temp_json if temperature is None else temperature
        msgs = list(messages)
        if not any("json" in m.content.lower() for m in msgs):  # Groq JSON mode requires the word in the prompt
            msgs.insert(0, ChatMessage(role="system", content="Reply with a single JSON object."))
        msg = await self.complete(msgs, temp, model=model or self.fast_model, json_mode=True,
                                  max_tokens=settings.llm_json_output_tokens)
        try:
            data = json.loads(msg.content)
        except json.JSONDecodeError:
            log.warning("groq returned invalid json: %.200s", msg.content)
            return {}
        return data if isinstance(data, dict) else {"items": data}

    async def transcribe(self, audio: bytes, filename: str, content_type: str,
                         language: str | None = None) -> Transcript:
        model = self.stt_model
        data = {"model": model, "response_format": "verbose_json", "temperature": "0"}
        if language:
            data["language"] = language
        r = await call_with_retry(self.provider, model, "stt", self.ring, lambda k: self._http.post(
            "/audio/transcriptions", data=data, files={"file": (filename, audio, content_type)},
            headers=self._auth(k)))
        body = r.json()
        return Transcript(text=(body.get("text") or "").strip(), language=body.get("language") or "",
                          duration_s=body.get("duration"))

    async def speak(self, text: str) -> bytes:
        model = self.tts_model
        body = {"model": model, "input": text, "voice": self.tts_voice, "response_format": "wav"}
        r = await call_with_retry(self.provider, model, "tts", self.ring, lambda k: self._http.post(
            "/audio/speech", json=body, headers=self._auth(k)))
        return r.content

    async def aclose(self) -> None:
        await self._http.aclose()


class TextLLM:
    """Ordered failover across OpenAI-compatible backends (Groq first, then Gemini's OpenAI endpoint).
    A backend that fails is skipped for TEXT_FAILOVER_COOLDOWN_S so a blocked provider costs one fast failure,
    not one per request. Streams fail over only before the first token. Audio falls back to Gemini native."""

    def __init__(self, backends: list[OpenAICompatClient], audio_fallback: Any = None) -> None:
        self.backends = backends
        self.audio_fallback = audio_fallback
        self._down_until: dict[str, float] = {}
        self._blocked: set[str] = set()  # answered 401/403/404: skipped even when everything else is busy
        self.active = backends[0].provider if backends else ""

    @property
    def status_detail(self) -> str:
        return " | ".join(b.status_detail for b in self.backends)

    @property
    def model(self) -> str:
        return next((b.model for b in self.backends if b.provider == self.active), "")

    def _usable(self, need: str = "model") -> list[OpenAICompatClient]:
        now = time.monotonic()
        ready = [b for b in self.backends if b.ring.keys and getattr(b, need)]
        up = [b for b in ready if self._down_until.get(b.provider, 0) <= now]
        if up:
            return up
        # Everything is cooling down: try the busy ones (429) soonest-first, never the blocked ones (404) (M-011).
        busy = [b for b in ready if b.provider not in self._blocked]
        return sorted(busy, key=lambda b: self._down_until.get(b.provider, 0)) or ready

    def _busy_retry(self, errors: list[ProviderError], need: str) -> OpenAICompatClient | None:
        """When every backend answered 429, one more try on the first non-blocked backend after a short wait."""
        if not errors or any(e.status != 429 for e in errors if e.provider not in self._blocked):
            return None
        return next((b for b in self.backends if b.ring.keys and getattr(b, need) and b.provider not in self._blocked),
                    None)

    def _failed(self, backend: OpenAICompatClient, exc: ProviderError) -> None:
        # 401/403/404 mean blocked or misconfigured, not busy: stop retrying it for much longer.
        blocked = exc.status in (401, 403, 404)
        if blocked:
            self._blocked.add(backend.provider)
        cooldown = settings.text_blocked_cooldown_s if blocked else settings.text_failover_cooldown_s
        self._down_until[backend.provider] = time.monotonic() + cooldown
        log.warning("text backend %s failed (%s), failing over", backend.provider, exc)

    async def _first(self, need: str, call: Any) -> Any:
        errors: list[ProviderError] = []
        for b in self._usable(need):
            try:
                result = await call(b)
                self.active = b.provider
                return result
            except ProviderError as exc:
                errors.append(exc)
                self._failed(b, exc)
        retry = self._busy_retry(errors, need)
        if retry is not None:
            await asyncio.sleep(settings.text_busy_retry_s)
            try:
                result = await call(retry)
                self.active = retry.provider
                return result
            except ProviderError as exc:
                errors.append(exc)
        if errors:
            raise errors[-1]
        raise ProviderError("text", f"no backend configured for {need}")

    async def ping(self) -> str:
        parts = []
        for b in self.backends:
            try:
                parts.append(f"{b.provider}: {await b.ping()}")
            except ProviderError as exc:
                parts.append(f"{b.provider}: unreachable ({exc.status or 'network'})")
        if not any("reachable," in p for p in parts):
            raise ProviderError("text", "; ".join(parts))
        return "; ".join(parts)

    async def complete(self, messages: list[ChatMessage], temperature: float, fast: bool = False,
                       **kw: Any) -> ChatMessage:
        need = "fast_model" if fast else "model"
        return await self._first(need, lambda b: b.complete(
            messages, temperature, model=b.fast_model if fast else b.model, **kw))

    async def stream_chat(self, messages: list[ChatMessage], temperature: float) -> AsyncIterator[str]:
        errors: list[ProviderError] = []
        candidates = self._usable("model")
        for attempt, b in enumerate(self._with_busy_retry(candidates, errors)):
            if attempt >= len(candidates):
                await asyncio.sleep(settings.text_busy_retry_s)
            stream = b.stream_chat(messages, temperature).__aiter__()
            try:
                # A backend that cannot produce a first token in time is skipped, not waited on (M-008).
                first = await asyncio.wait_for(stream.__anext__(), timeout=settings.text_first_token_timeout_s)
            except StopAsyncIteration:
                return
            except (ProviderError, asyncio.TimeoutError) as exc:
                await stream.aclose()
                err = exc if isinstance(exc, ProviderError) else ProviderError(b.provider, "no first token in time")
                errors.append(err)
                self._failed(b, err)
                continue
            self.active = b.provider
            yield first
            async for token in stream:
                yield token
            return
        raise errors[-1] if errors else ProviderError("text", "no chat backend configured")

    def _with_busy_retry(self, candidates: list[OpenAICompatClient], errors: list[ProviderError]):
        """Yield each candidate; if all failed with 429, yield one more after the caller sleeps (see stream_chat)."""
        yield from candidates
        retry = self._busy_retry(errors, "model")
        if retry is not None:
            yield retry

    async def chat(self, messages: list[ChatMessage], temperature: float) -> str:
        return (await self.complete(messages, temperature)).content

    async def chat_json(self, messages: list[ChatMessage], temperature: float | None = None) -> dict:
        return await self._first("fast_model", lambda b: b.chat_json(messages, temperature))

    async def transcribe(self, audio: bytes, filename: str, content_type: str,
                         language: str | None = None) -> Transcript:
        try:
            return await self._first("stt_model", lambda b: b.transcribe(audio, filename, content_type, language))
        except ProviderError:
            if self.audio_fallback is None:
                raise
            return await self.audio_fallback.transcribe(audio, content_type)

    async def speak(self, text: str) -> bytes:
        try:
            return await self._first("tts_model", lambda b: b.speak(text))
        except ProviderError:
            if self.audio_fallback is None:
                raise
            return await self.audio_fallback.speak(text)

    async def aclose(self) -> None:
        for b in self.backends:
            await b.aclose()
        if self.audio_fallback is not None:
            await self.audio_fallback.aclose()


def build_text_llm(transport: httpx.AsyncBaseTransport | None = None) -> TextLLM:
    from backend.llm.gemini import GeminiClient  # local import keeps module import order simple
    groq = OpenAICompatClient("groq", settings.groq_base_url, settings.groq_api_keys, settings.groq_chat_model,
                              settings.groq_fast_model, settings.groq_stt_model, settings.groq_tts_model,
                              settings.groq_tts_voice, transport=transport)
    gemini = OpenAICompatClient("gemini", settings.gemini_openai_base_url, settings.gemini_api_key,
                                settings.gemini_chat_model, settings.gemini_fast_model,
                                reasoning_effort=settings.gemini_reasoning_effort, transport=transport)
    # Free-tier quota is per model, so a second Gemini model absorbs 429s on the first (M-011).
    backup = OpenAICompatClient("gemini-backup", settings.gemini_openai_base_url, settings.gemini_api_key,
                                settings.gemini_backup_model, settings.gemini_backup_model, transport=transport)
    order = {"groq": groq, "gemini": gemini, "gemini-backup": backup}
    backends = [order[name] for name in settings.text_providers if name in order]
    return TextLLM(backends, audio_fallback=GeminiClient(transport=transport))
