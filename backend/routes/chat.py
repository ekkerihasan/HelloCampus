"""POST /api/chat: Server-Sent Events stream of meta, token, sources, done."""
import json
import logging
from typing import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from backend.llm.chat import ChatEvent, ChatRequest, run_turn
from backend.routes.deps import optional, require

log = logging.getLogger("hello_campus.routes.chat")
router = APIRouter()


def sse(ev: ChatEvent) -> str:
    return f"event: {ev.event}\ndata: {json.dumps(ev.data, ensure_ascii=False)}\n\n"


@router.post("/api/chat")
async def chat(req: ChatRequest, llm=Depends(require("llm")), store=Depends(optional("rag")),
               mem=Depends(optional("memory"))) -> StreamingResponse:
    async def gen() -> AsyncIterator[str]:
        try:
            async for ev in run_turn(req, llm, store, mem):
                yield sse(ev)
        except Exception as exc:  # noqa: BLE001, surface to UI instead of a dropped stream
            log.exception("chat turn failed")
            yield sse(ChatEvent(event="error", data={"message": f"Something went wrong: {exc}"}))

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
