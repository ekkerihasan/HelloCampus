"""Async Ollama client: streaming chat with per-call temperature, JSON mode, and embeddings."""
import json
import logging
import time
from typing import AsyncIterator

import httpx
from pydantic import BaseModel

from backend.config import settings

log = logging.getLogger("hello_campus.llm")


class ChatMessage(BaseModel):
    role: str  # system | user | assistant
    content: str


class OllamaClient:
    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        self.base_url = (base_url or settings.ollama_url).rstrip("/")
        self.model = model or settings.llm_model
        self.embed_model = settings.embed_model
        self._http = httpx.AsyncClient(base_url=self.base_url, timeout=settings.llm_timeout_s)
        self.status_detail = ""

    async def check(self) -> "OllamaClient":
        """Verify Ollama is up and pick the configured model, or the fallback if only that exists."""
        r = await self._http.get("/api/tags")
        r.raise_for_status()
        names = {m["name"] for m in r.json().get("models", [])}
        has = lambda n: n in names or f"{n}:latest" in names  # noqa: E731
        if not has(self.model):
            if has(settings.llm_fallback_model):
                log.warning("model %s missing, using fallback %s", self.model, settings.llm_fallback_model)
                self.model = settings.llm_fallback_model
            else:
                raise RuntimeError(f"model {self.model} not pulled in Ollama")
        if not has(self.embed_model):
            raise RuntimeError(f"embedding model {self.embed_model} not pulled in Ollama")
        self.status_detail = f"llm={self.model} embed={self.embed_model}"
        return self

    async def warm_up(self) -> "OllamaClient":
        """Load both models into RAM at startup so the first visitor does not wait for a cold load."""
        start = time.perf_counter()
        r = await self._http.post("/api/generate", json={"model": self.model, "keep_alive": settings.llm_keep_alive})
        r.raise_for_status()
        r = await self._http.post("/api/embed", json={"model": self.embed_model, "input": ["warm up"],
                                                  "keep_alive": settings.llm_keep_alive})
        r.raise_for_status()
        log.info("warm up %d ms", (time.perf_counter() - start) * 1000)
        return self

    def _payload(self, messages: list[ChatMessage], temperature: float, stream: bool, json_mode: bool) -> dict:
        payload: dict = {
            "model": self.model,
            "messages": [m.model_dump() for m in messages],
            "stream": stream,
            "options": {"temperature": temperature, "num_ctx": settings.llm_num_ctx,
                        "num_predict": settings.llm_json_output_tokens if json_mode else settings.llm_max_output_tokens},
            "think": False,
            "keep_alive": settings.llm_keep_alive,
        }
        if json_mode:
            payload["format"] = "json"
        return payload

    async def stream_chat(self, messages: list[ChatMessage], temperature: float) -> AsyncIterator[str]:
        """Yield text tokens as they arrive. Logs first-token latency."""
        start = time.perf_counter()
        first = True
        async with self._http.stream("POST", "/api/chat", json=self._payload(messages, temperature, True, False)) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                if chunk.get("error"):
                    raise RuntimeError(chunk["error"])
                token = chunk.get("message", {}).get("content", "")
                if token:
                    if first:
                        log.info("llm first token %d ms (temp %.1f)", (time.perf_counter() - start) * 1000, temperature)
                        first = False
                    yield token
                if chunk.get("done"):
                    break

    async def chat(self, messages: list[ChatMessage], temperature: float) -> str:
        return "".join([t async for t in self.stream_chat(messages, temperature)])

    async def chat_json(self, messages: list[ChatMessage], temperature: float | None = None) -> dict:
        """Non-streaming JSON-mode call. Returns {} if the model emits invalid JSON."""
        temp = settings.temp_json if temperature is None else temperature
        r = await self._http.post("/api/chat", json=self._payload(messages, temp, False, True))
        r.raise_for_status()
        text = r.json().get("message", {}).get("content", "")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            log.warning("llm returned invalid json: %.200s", text)
            return {}
        return data if isinstance(data, dict) else {"items": data}

    async def embed(self, texts: list[str]) -> list[list[float]]:
        r = await self._http.post("/api/embed", json={"model": self.embed_model, "input": texts,
                                                      "keep_alive": settings.llm_keep_alive})
        r.raise_for_status()
        return r.json()["embeddings"]

    async def aclose(self) -> None:
        await self._http.aclose()
