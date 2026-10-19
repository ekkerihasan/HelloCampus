"""Visitor create, fetch, resume by code, and character preference."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from backend.llm.characters import CharacterName
from backend.memory.store import PURPOSES, MemoryStore, Visitor
from backend.routes.deps import require

router = APIRouter(prefix="/api/visitor")


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
