"""Hiring and student endpoints. Every student lookup rechecks the opt-in list."""
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from backend.hiring import service
from backend.memory.store import MemoryStore, RoleSpec, Visitor
from backend.providers.retry import ProviderError
from backend.routes.deps import require

router = APIRouter()


class RoleRequest(BaseModel):
    visitor_id: str
    description: str = Field(min_length=3, max_length=6000)


class VisitRequest(BaseModel):
    visitor_id: str


class ShortlistRequest(VisitRequest):
    entity_id: str


class CompareRequest(BaseModel):
    entity_ids: list[str] = Field(min_length=2, max_length=2)


def visitor(mem: MemoryStore, visitor_id: str) -> Visitor:
    v = mem.get(visitor_id)
    if v is None:
        raise HTTPException(404, "Visitor not found")
    return v


def records_for(entity_id: str):
    records = service.student_data().get(entity_id.lower())
    if not records:
        raise HTTPException(404, "No currently opted-in student record found")
    return records


@router.post("/api/hiring/role")
async def role(body: RoleRequest, mem=Depends(require("memory")), llm=Depends(require("llm"))) -> RoleSpec:
    await asyncio.to_thread(visitor, mem, body.visitor_id)
    try:
        spec = await service.intake(llm, body.description)
    except ProviderError as exc:
        raise HTTPException(503, f"{exc.user_message} Please try again in a moment.") from exc
    await asyncio.to_thread(mem.update, body.visitor_id, role=spec, character="analyst")
    return spec


@router.post("/api/hiring/match")
async def match(body: VisitRequest, mem=Depends(require("memory")), llm=Depends(require("llm")),
                store=Depends(require("rag"))) -> list[service.Candidate]:
    v = await asyncio.to_thread(visitor, mem, body.visitor_id)
    # Keyword-only searches ("Skills: React") have skills but no title; either is enough to match on.
    if not (v.role.title or v.role.must_have or v.role.nice_to_have):
        raise HTTPException(422, "Describe the role or pick at least one skill first")
    try:
        return await service.match(llm, store, v.role)
    except ProviderError as exc:
        raise HTTPException(503, f"{exc.user_message} Your role is saved, so just try Find matches again.") from exc


@router.post("/api/hiring/compare")
def compare(body: CompareRequest) -> list[service.Candidate]:
    return [service.candidate(key.lower(), records_for(key)) for key in body.entity_ids]


@router.get("/api/hiring/shortlist/{visitor_id}")
def shortlist(visitor_id: str, mem=Depends(require("memory"))) -> list[service.Candidate]:
    v, data = visitor(mem, visitor_id), service.student_data()
    return [service.candidate(key, data[key]) for key in v.shortlist if key in data]


@router.post("/api/hiring/shortlist")
def shortlist_add(body: ShortlistRequest, mem=Depends(require("memory"))) -> list[str]:
    visitor(mem, body.visitor_id)
    records_for(body.entity_id)
    mem.shortlist_add(body.visitor_id, body.entity_id.lower())
    return [c.entity_id for c in shortlist(body.visitor_id, mem)]


@router.delete("/api/hiring/shortlist/{visitor_id}/{entity_id}")
def shortlist_remove(visitor_id: str, entity_id: str, mem=Depends(require("memory"))) -> list[str]:
    visitor(mem, visitor_id)
    mem.shortlist_remove(visitor_id, entity_id.lower())
    return [c.entity_id for c in shortlist(visitor_id, mem)]


@router.post("/api/hiring/interview/{entity_id}")
async def interview(entity_id: str, llm=Depends(require("llm"))) -> list[service.EvidenceClaim]:
    questions = await service.interview(llm, await asyncio.to_thread(records_for, entity_id))
    await asyncio.to_thread(records_for, entity_id)
    return questions


@router.get("/api/hiring/export/{visitor_id}", response_class=PlainTextResponse)
def export(visitor_id: str, mem=Depends(require("memory"))):
    v = visitor(mem, visitor_id)
    people = shortlist(visitor_id, mem)
    lines = [f"# Shortlist: {v.role.title or 'Campus candidates'}", ""]
    for c in people:
        lines.extend([f"## {c.name} (@{c.entity_id})", c.headline,
                      "Languages recorded: " + ", ".join(c.languages), "Evidence:"])
        lines.extend(f"- {url}" for url in c.sources)
        lines.append("")
    return PlainTextResponse("\n".join(lines), media_type="text/markdown",
        headers={"Content-Disposition": 'attachment; filename="hello-campus-shortlist.md"'})


@router.get("/api/students/{entity_id}")
def profile(entity_id: str) -> service.Candidate:
    return service.candidate(entity_id.lower(), records_for(entity_id))


@router.post("/api/students/{entity_id}/readme")
async def readme(entity_id: str, llm=Depends(require("llm"))) -> dict[str, str]:
    result = await service.improved_readme(llm, await asyncio.to_thread(records_for, entity_id))
    await asyncio.to_thread(records_for, entity_id)
    return result
