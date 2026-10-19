"""FastAPI entry point. Models are loaded once at startup and reported in /api/health."""
import logging
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend import components  # noqa: F401, registers startup loaders
from backend.config import settings
from backend.routes import chat, visitor, hiring
from backend.status import registry

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("hello_campus")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await registry.load_all()
    yield
    mem = registry.get("memory")
    if mem:
        await asyncio.to_thread(mem.close)
    llm = registry.get("llm")
    if llm:
        await llm.aclose()
    rag = registry.get("rag")
    if rag:
        await rag.llm.aclose()


app = FastAPI(title="Hello Campus", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(chat.router)
app.include_router(visitor.router)
app.include_router(hiring.router)


@app.get("/api/health")
async def health() -> dict:
    data = registry.health()
    rag = registry.get("rag")
    if rag is not None:  # refresh counts after `make ingest`
        data["components"]["rag"]["detail"] = await asyncio.to_thread(lambda: rag.status_detail)
    return data
