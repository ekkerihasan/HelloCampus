"""FastAPI entry point. Clients load once at startup; /api/health reports components and provider reachability."""
import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from backend import components  # noqa: F401, registers startup loaders
from backend.config import settings
from backend.providers import usage
from backend.routes import chat, gesture, hiring, live, quiz, speech, tools, visit, visitor
from backend.status import registry

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("hello_campus")
_provider_cache: dict[str, object] = {"at": 0.0, "data": {}}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await registry.load_all()
    try:
        yield
    finally:
        await registry.close_all()


app = FastAPI(title="Hello Campus", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])

for module in (chat, visitor, hiring, speech, tools, live, visit, quiz, gesture):
    app.include_router(module.router)


async def _probe(name: str) -> dict:
    client = registry.get(name)
    if client is None:
        return {"reachable": False, "detail": "client not loaded"}
    return await _probe_client(client)


async def _probe_client(client) -> dict:
    start = time.perf_counter()
    try:
        detail = await asyncio.wait_for(client.ping(), timeout=settings.health_timeout_s)
        return {"reachable": True, "detail": detail, "ms": int((time.perf_counter() - start) * 1000)}
    except Exception as exc:  # noqa: BLE001, health must report, never raise
        return {"reachable": False, "detail": getattr(exc, "user_message", None) or type(exc).__name__,
                "error": str(exc)[:200]}


@app.get("/api/health")
async def health(refresh: bool = False) -> dict:
    data = registry.health()
    rag = registry.get("rag")
    if rag is not None:  # refresh counts after `make ingest`
        data["components"]["rag"]["detail"] = await asyncio.to_thread(lambda: rag.status_detail)
    if refresh or time.time() - float(_provider_cache["at"]) > settings.health_cache_s:
        text = registry.get("llm")
        backends = list(getattr(text, "backends", []))
        results = await asyncio.gather(_probe("gemini"), *(_probe_client(b) for b in backends))
        probes = {"gemini": results[0]}
        probes.update({f"text_{b.provider}": r for b, r in zip(backends, results[1:])})
        _provider_cache.update(at=time.time(), data=probes)
    data["providers"] = _provider_cache["data"]
    data["text_active"] = getattr(registry.get("llm"), "active", "")
    data["live_enabled"] = settings.live_enabled
    # Healthy when Gemini (Live, vision, embeddings) and at least one text backend are reachable.
    text_ok = any(v.get("reachable") for k, v in data["providers"].items() if k.startswith("text_"))
    data["ok"] = bool(data["providers"].get("gemini", {}).get("reachable")) and text_ok
    return data


@app.get("/debug", response_class=HTMLResponse)
def debug() -> str:
    """Hidden usage counter (ADDENDUM-01 section 8). No keys or prompts are logged."""
    s = usage.summary()
    rows = "".join(f"<tr><td>{k}</td><td>{v}</td><td>{s['tokens'].get(k, 0)}</td></tr>"
                   for k, v in sorted(s["calls"].items()))
    return (f"<!doctype html><meta name=viewport content='width=device-width'><title>Usage</title>"
            f"<body style='font-family:system-ui;padding:16px'><h1>External calls</h1>"
            f"<p>Rate limited (429): {s['rate_limited']}</p><table border=1 cellpadding=4>"
            f"<tr><th>provider/model/op</th><th>calls</th><th>tokens</th></tr>{rows}</table>")
