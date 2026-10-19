"""Gemini REST client: embeddings (document vs query task types), Flash vision for Look, and ephemeral
Live tokens. The API key never leaves the backend; the browser only receives the ephemeral token."""
import base64
import io
import json
import logging
import wave
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from backend.config import settings
from backend.providers.retry import KeyRing, ProviderError, call_with_retry, timeout

log = logging.getLogger("hello_campus.gemini")
PROVIDER = "gemini"
DOC_TASK = "RETRIEVAL_DOCUMENT"
QUERY_TASK = "RETRIEVAL_QUERY"
TRANSCRIBE_SCHEMA = {"type": "OBJECT", "properties": {"text": {"type": "STRING"}, "language": {"type": "STRING"}},
                     "required": ["text", "language"]}


def _tokens(response: httpx.Response) -> tuple[int | None, int | None]:
    try:
        u = response.json().get("usageMetadata") or {}
    except ValueError:
        return None, None
    return u.get("promptTokenCount"), u.get("candidatesTokenCount")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class GeminiClient:
    def __init__(self, key: str | None = None, transport: httpx.AsyncBaseTransport | None = None) -> None:
        key = settings.gemini_api_key if key is None else key
        self.ring = KeyRing(PROVIDER, [key] if key else [])
        self.embed_model = settings.gemini_embed_model
        self.vision_model = settings.gemini_vision_model
        self._http = httpx.AsyncClient(base_url=settings.gemini_base_url, timeout=timeout(), transport=transport)
        self.status_detail = (f"embed={self.embed_model or 'unset'} vision={self.vision_model or 'unset'} "
                              f"live={settings.gemini_live_model or 'unset'}")

    @staticmethod
    def _auth(key: str) -> dict[str, str]:
        return {"x-goog-api-key": key}

    async def list_models(self) -> list[str]:
        r = await call_with_retry(PROVIDER, "models", "list_models", self.ring, lambda k: self._http.get(
            "/v1beta/models", params={"pageSize": 1000}, headers=self._auth(k)))
        return sorted(m.get("name", "").removeprefix("models/") for m in r.json().get("models", []))

    async def ping(self) -> str:
        ids = set(await self.list_models())
        missing = [m for m in (settings.gemini_embed_model, settings.gemini_vision_model, settings.gemini_live_model)
                   if m and m not in ids]
        return f"reachable, {len(ids)} models" + (f", MISSING {missing}" if missing else "")

    async def embed(self, texts: list[str], task_type: str = DOC_TASK,
                    titles: list[str] | None = None) -> list[list[float]]:
        model = self.embed_model
        titles = titles or ["none"] * len(texts)
        out: list[list[float]] = []
        for i in range(0, len(texts), settings.embed_batch):
            batch = list(zip(texts[i:i + settings.embed_batch], titles[i:i + settings.embed_batch]))
            body = {"requests": [self._embed_request(model, t, title, task_type) for t, title in batch]}
            r = await call_with_retry(PROVIDER, model, f"embed_{task_type.lower()}", self.ring,
                lambda k, b=body: self._http.post(f"/v1beta/models/{model}:batchEmbedContents", json=b,
                                                  headers=self._auth(k)))
            vectors = [e.get("values", []) for e in r.json().get("embeddings", [])]
            if len(vectors) != len(batch):
                raise ProviderError(PROVIDER, f"embedding count mismatch {len(vectors)} != {len(batch)}")
            out.extend(vectors)
        return out

    @staticmethod
    def _embed_request(model: str, text: str, title: str, task_type: str) -> dict:
        """gemini-embedding-2 takes task hints as text templates; 001 takes taskType (M-003, T0.2 research)."""
        text = text[:settings.embed_max_chars]
        req: dict[str, Any] = {"model": f"models/{model}", "outputDimensionality": settings.embed_dimensions}
        if settings.embed_task_mode == "task_type":
            req.update(taskType=task_type, content={"parts": [{"text": text}]})
        else:
            template = settings.embed_query_template if task_type == QUERY_TASK else settings.embed_doc_template
            req["content"] = {"parts": [{"text": template.format(title=title or "none", text=text)}]}
        return req

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed([text], QUERY_TASK))[0]

    async def generate(self, parts: list[dict], temperature: float, system: str = "",
                       json_schema: dict | None = None, model: str | None = None) -> str:
        model = model or self.vision_model
        config: dict[str, Any] = {"temperature": temperature, "maxOutputTokens": settings.llm_json_output_tokens}
        if json_schema:
            config.update(responseMimeType="application/json", responseSchema=json_schema)
        body: dict[str, Any] = {"contents": [{"role": "user", "parts": parts}], "generationConfig": config}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        r = await call_with_retry(PROVIDER, model, "generate", self.ring, lambda k: self._http.post(
            f"/v1beta/models/{model}:generateContent", json=body, headers=self._auth(k)), _tokens)
        candidates = r.json().get("candidates") or []
        if not candidates:
            raise ProviderError(PROVIDER, "no candidates returned (possibly blocked)")
        return "".join(p.get("text", "") for p in candidates[0].get("content", {}).get("parts", []))

    async def look(self, image: bytes, mime: str, question: str, system: str, schema: dict) -> dict:
        parts = [{"inline_data": {"mime_type": mime, "data": base64.b64encode(image).decode()}},
                 {"text": question}]
        text = await self.generate(parts, settings.temp_json, system=system, json_schema=schema)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            log.warning("look returned invalid json: %.200s", text)
            return {}
        return data if isinstance(data, dict) else {}

    async def mint_live_token(self, config: dict | None = None) -> dict:
        """Ephemeral v1beta token for one Live session (M-002). `config` locks the model, system instruction and
        tools on the server, so the browser cannot reuse the token for anything else."""
        model = settings.gemini_live_model
        now = datetime.now(timezone.utc)
        body: dict[str, Any] = {"uses": settings.live_token_uses,
                "expireTime": _iso(now + timedelta(seconds=settings.live_token_ttl_s)),
                "newSessionExpireTime": _iso(now + timedelta(seconds=settings.live_new_session_window_s))}
        if config is not None:
            body.update(live_setup(model, config))
        r = await call_with_retry(PROVIDER, model, "live_token", self.ring, lambda k: self._http.post(
            "/v1beta/auth_tokens", json=body, headers=self._auth(k)))
        data = r.json()
        return {"token": data.get("name", ""), "expire_time": body["expireTime"], "model": model}

    async def transcribe(self, audio: bytes, mime: str) -> "Transcript":
        """Fallback STT when no Whisper backend is reachable."""
        from backend.llm.client import Transcript
        parts = [{"inline_data": {"mime_type": mime, "data": base64.b64encode(audio).decode()}},
                 {"text": "Transcribe this speech exactly, in the language spoken. Return text and the ISO 639-1 "
                          "language code. If there is no speech, return empty text."}]
        text = await self.generate(parts, settings.temp_json, json_schema=TRANSCRIBE_SCHEMA)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = {}
        return Transcript(text=str(data.get("text", "")).strip(), language=str(data.get("language", "")))

    async def speak(self, text: str) -> bytes:
        """Fallback TTS. Gemini returns raw 24 kHz 16-bit PCM, wrapped here as WAV."""
        model = settings.gemini_tts_model
        config: dict[str, Any] = {"responseModalities": ["AUDIO"]}
        if settings.gemini_tts_voice:
            config["speechConfig"] = {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": settings.gemini_tts_voice}}}
        body = {"contents": [{"parts": [{"text": text}]}], "generationConfig": config}
        r = await call_with_retry(PROVIDER, model, "tts", self.ring, lambda k: self._http.post(
            f"/v1beta/models/{model}:generateContent", json=body, headers=self._auth(k)), _tokens)
        parts = ((r.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        blob = next((p.get("inlineData") or p.get("inline_data") for p in parts
                     if p.get("inlineData") or p.get("inline_data")), None)
        if not blob:
            raise ProviderError(PROVIDER, "tts returned no audio")
        return pcm_to_wav(base64.b64decode(blob["data"]), settings.gemini_tts_sample_rate)

    async def aclose(self) -> None:
        await self._http.aclose()


GENERATION_FIELDS = ("responseModalities", "temperature", "speechConfig", "topP", "topK", "maxOutputTokens")
# Left to the browser: the resume handle changes per reconnect. Everything else in the config is locked.
CLIENT_FIELDS = ("sessionResumption", "contextWindowCompression")


def live_setup(model: str, config: dict) -> dict:
    """LiveConnectConfig (the shape the browser SDK takes) -> the REST auth token constraint. The REST field is
    bidiGenerateContentSetup with generation settings nested under generationConfig (read from @google/genai 2.30
    liveConnectConstraintsToMldev, since liveConnectConstraints is rejected by REST with HTTP 400). The API requires
    every field in the setup to be listed in fieldMask, so client-controlled fields are left out of the setup."""
    setup: dict[str, Any] = {"model": f"models/{model}"}
    generation = {k: config[k] for k in GENERATION_FIELDS if k in config}
    if generation:
        setup["generationConfig"] = generation
    setup.update({k: v for k, v in config.items() if k not in GENERATION_FIELDS and k not in CLIENT_FIELDS})
    mask = [f"generationConfig.{k}" for k in generation] + [k for k in setup if k != "generationConfig"]
    return {"bidiGenerateContentSetup": setup, "fieldMask": ",".join(mask)}


def pcm_to_wav(pcm: bytes, rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()
