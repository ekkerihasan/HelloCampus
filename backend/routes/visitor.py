"""Visitor create, fetch, resume by code, character preference, and Live turn memory."""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from backend.llm.characters import CharacterName
from backend.config import settings
from backend.memory.extract import extract_and_save
from backend.memory.store import PURPOSES, MemoryStore, Visitor
from backend.routes.deps import require

router = APIRouter(prefix="/api/visitor")
log = logging.getLogger("hello_campus.visitor")


class CreateVisitor(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    purpose: str = Field(default="", max_length=60)

    @field_validator("name")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Please enter your name")
        return value.strip()


class CharacterUpdate(BaseModel):
    character: CharacterName


@router.get("/purposes")
def purposes() -> list[str]:
    return list(PURPOSES)


@router.post("")
def create(body: CreateVisitor, mem: MemoryStore = Depends(require("memory"))) -> Visitor:
    return mem.create(body.name, body.purpose)


@router.get("/resume/{code}")
def resume(code: str, mem: MemoryStore = Depends(require("memory"))) -> Visitor:
    v = mem.by_code(code)
    if not v:
        raise HTTPException(404, "No visitor with that code. Check the four characters and try again.")
    return v


@router.get("/{visitor_id}")
def get(visitor_id: str, mem: MemoryStore = Depends(require("memory"))) -> Visitor:
    v = mem.get(visitor_id)
    if not v:
        raise HTTPException(404, "Visitor not found")
    return v


@router.put("/{visitor_id}/character")
def set_character(visitor_id: str, body: CharacterUpdate, mem: MemoryStore = Depends(require("memory"))) -> Visitor:
    v = mem.update(visitor_id, character=body.character.value)
    if not v:
        raise HTTPException(404, "Visitor not found")
    return v


class LiveTurn(BaseModel):
    user: str = Field(min_length=1, max_length=settings.chat_max_message_chars)
    assistant: str = Field(default="", max_length=settings.chat_max_message_chars)


@router.post("/{visitor_id}/turn")
async def live_turn(visitor_id: str, body: LiveTurn, mem: MemoryStore = Depends(require("memory")),
                    llm=Depends(require("llm"))) -> dict:
    """Live voice transcripts feed the same memory as chat (ADDENDUM-01 5.2): last ten turns plus extracted facts."""
    v = await asyncio.to_thread(mem.get, visitor_id)
    if not v:
        raise HTTPException(404, "Visitor not found")
    await asyncio.to_thread(mem.add_turn, v.id, "user", body.user)
    if body.assistant:
        await asyncio.to_thread(mem.add_turn, v.id, "assistant", body.assistant)
    try:
        await asyncio.wait_for(extract_and_save(llm, mem, v, body.user, body.assistant),
                               timeout=settings.memory_extract_timeout_s)
    except Exception:  # noqa: BLE001, memory must never break the conversation
        log.exception("live memory extraction failed")
        return {"saved": False}
    return {"saved": True}
