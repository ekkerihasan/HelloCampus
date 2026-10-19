"""The ten tools from ADDENDUM-01 section 6. Thin wrappers over services; results carry `sources` where relevant,
and the UI renders citation chips only from these results, never from model text."""
import asyncio
from typing import Literal

from pydantic import BaseModel, Field

from backend.config import settings
from backend.hiring import service as hiring
from backend.memory.store import Visitor
from backend.rag.search import search_campus as search
from backend.rag.local_recommend import rank_places, vegetarian_request
from backend.tools.registry import ToolContext, ToolError, tool

REFUSAL_NOTE = ("Nothing in the campus data answers this yet. Say you don't have that yet and suggest the help desk "
                "or a student volunteer. Do not guess.")
MAX_REMEMBERED = 12


async def _visitor(ctx: ToolContext) -> Visitor:
    mem = ctx.get("memory")
    if mem is None or not ctx.visitor_id:
        raise ToolError("No visitor session. Ask the visitor to start or resume their visit.")
    v = await asyncio.to_thread(mem.get, ctx.visitor_id)
    if v is None:
        raise ToolError("Visitor not found.")
    return v


class SearchArgs(BaseModel):
    query: str = Field(min_length=1, max_length=500, description="The visitor's question, in their own words")
    collections: list[Literal["campus", "achievements", "students", "locality"]] | None = Field(
        None, description="Optional: limit to these knowledge collections")


@tool("search_campus", "Search the campus knowledge base: college, departments, clubs, facilities, achievements, "
      "student projects and nearby places. Use for any factual question. Not for event times (use get_schedule).",
      SearchArgs)
async def search_campus(ctx: ToolContext, a: SearchArgs) -> dict:
    store = ctx.get("rag")
    if store is None:
        raise ToolError("The knowledge base is not loaded right now.")
    k = settings.rag_top_k_voice if ctx.mode == "voice" else settings.rag_top_k_chat
    # The model sometimes shortens the question ("stats about Anjuman" -> "Anjuman"), so the vector search uses the
    # visitor's own words (already embedded in the background by the chat turn) and BM25 also gets the model query.
    words = ctx.user_message.strip()
    if words:
        r = await search(store, ctx.get("llm"), words, a.collections, k=k, extra_keywords=a.query)
    else:
        r = await search(store, ctx.get("llm"), a.query, a.collections, k=k)
    if r.refusal:
        return {"refusal": True, "note": REFUSAL_NOTE, "sources": []}
    return {"snippets": r.snippets, "sources": [s.model_dump() for s in r.sources],
            "note": "Cite facts with their [n] number. Use only these snippets."}


class LocalArgs(BaseModel):
    type: Literal["food", "travel", "place", "practical"] = Field(description="Kind of local tip")
    query: str | None = Field(None, max_length=300, description="Optional: what they want, e.g. budget lunch")
    veg: bool | None = Field(None, description="Optional: true for vegetarian options only")


@tool("get_local_tips", "Hand-curated food, travel, places and practical tips near campus (ATM, pharmacy, stays). "
      "Supports a vegetarian filter.", LocalArgs)
async def get_local_tips(ctx: ToolContext, a: LocalArgs) -> dict:
    sched = ctx.get("schedule")
    if sched is None:
        raise ToolError("Local tips are not loaded right now.")
    # Keep the visitor's words as well as a model-rephrased query. An explicit dietary request
    # must survive a shortened tool call in both text and voice paths.
    query = " ".join(dict.fromkeys(filter(None, (ctx.user_message.strip(), a.query))))
    veg = a.veg
    if a.type == "food" and vegetarian_request(query):
        veg = True
    items = await asyncio.to_thread(sched.local, a.type, veg, None)
    note = ""
    if veg and not items:
        # No confirmed veg place: offer places whose veg options are unknown, and say so plainly.
        items = await asyncio.to_thread(sched.local, a.type, None, None, True)
        if items:
            note = ("None of these places has confirmed vegetarian options. Say that veg options are not confirmed "
                    "and suggest asking the restaurant.")
    items = rank_places(items, query)
    if not items:
        return {"items": [], "refusal": True, "note": REFUSAL_NOTE, "sources": []}
    limit = settings.rag_top_k_voice if ctx.mode == "voice" else settings.rag_top_k_chat
    items = items[:limit]
    cautions = [note] if note else []
    if a.type == "food":
        cautions.append("Use only recorded details. Blank prices, distances and hours are unknown. "
                        "Listed hours do not confirm a place is open now; do not claim dietary suitability "
                        "beyond the recorded vegetarian flag.")
    note = " ".join(cautions)
    return {"items": items, **({"note": note} if note else {}), "sources": [{"title": it["name"], "url": it.get("source_url", "curated"), "collection": "locality",
                                         "last_checked": it["last_checked"]} for it in items]}


class ScheduleArgs(BaseModel):
    date: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="Optional: YYYY-MM-DD")
    venue: str | None = Field(None, max_length=100, description="Optional: venue name or part of it")


@tool("get_schedule", "Exact event schedule, timings, venues and contacts. Always use this for when or where an "
      "event happens.", ScheduleArgs)
async def get_schedule(ctx: ToolContext, a: ScheduleArgs) -> dict:
    sched = ctx.get("schedule")
    if sched is None:
        raise ToolError("The schedule is not loaded right now.")
    events = await asyncio.to_thread(sched.schedule, a.date, a.venue)
    if not events:
        return {"events": [], "note": "No confirmed schedule entry matches. Say so; do not guess a time."}
    return {"events": events, "sources": [{"title": e["title"], "url": e["source_url"], "collection": "schedule",
                                           "last_checked": e["last_checked"]} for e in events]}


class NoArgs(BaseModel):
    pass


@tool("get_visitor_profile", "What we know about this visitor: name, purpose, language, saved facts, shortlist.",
      NoArgs)
async def get_visitor_profile(ctx: ToolContext, a: NoArgs) -> dict:
    v = await _visitor(ctx)
    facts = [f"{k}: {', '.join(map(str, val))}" for k, val in v.facts.items() if val]
    return {"name": v.name, "purpose": v.purpose, "language": v.language, "facts": facts, "shortlist": v.shortlist}


class RememberArgs(BaseModel):
    fact: str = Field(min_length=2, max_length=200, description="The fact to remember, in a short phrase")


@tool("remember", "Save a fact only when the visitor explicitly asks you to remember something.", RememberArgs,
      blocking=False)
async def remember(ctx: ToolContext, a: RememberArgs) -> dict:
    v = await _visitor(ctx)
    notes = [n for n in v.facts.get("notes", []) if n.lower() != a.fact.strip().lower()]
    notes = (notes + [a.fact.strip()])[-MAX_REMEMBERED:]
    await asyncio.to_thread(ctx.get("memory").update, v.id, facts={**v.facts, "notes": notes})
    return {"ok": True}


class LookArgs(BaseModel):
    question: str | None = Field(None, max_length=300, description="Optional: what the visitor wants to know")


@tool("look", "Take one photo with the visitor's camera and read it: posters, notice boards, menus, signs. Use when "
      "they say look at this or ask about something in front of them.", LookArgs, chat=False, client_side=True)
async def look(ctx: ToolContext, a: LookArgs) -> dict:
    return {"error": "look runs in the browser"}


class RoleArgs(BaseModel):
    description: str = Field(min_length=3, max_length=6000, description="The role in the recruiter's words or a JD")


@tool("hiring_set_role", "Save the role a recruiter is hiring for, structured into must-haves and nice-to-haves.",
      RoleArgs)
async def hiring_set_role(ctx: ToolContext, a: RoleArgs) -> dict:
    v = await _visitor(ctx)
    role = await hiring.intake(ctx.get("llm"), a.description)
    await asyncio.to_thread(ctx.get("memory").update, v.id, role=role)
    return {"role": role.model_dump()}


class MatchArgs(BaseModel):
    limit: int | None = Field(None, ge=1, le=5, description="Optional: how many candidates, 1 to 5")


@tool("hiring_match", "Find opted-in students matching the saved role. Every reason links to stored evidence.",
      MatchArgs)
async def hiring_match(ctx: ToolContext, a: MatchArgs) -> dict:
    v = await _visitor(ctx)
    if not (v.role.title or v.role.must_have or v.role.nice_to_have):
        return {"candidates": [], "note": "No role saved yet. Ask what they are hiring for, then hiring_set_role."}
    if ctx.get("rag") is None:
        raise ToolError("The knowledge base is not loaded right now.")
    found = await hiring.match(ctx.get("llm"), ctx.get("rag"), v.role)  # runs the evidence post-check
    found = found[:a.limit or 3]
    if not found:
        return {"candidates": [], "note": "No opted-in student has stored evidence for this role yet. Say so."}
    return {"candidates": [{"id": c.entity_id, "name": c.name, "reasons": [cl.text for cl in c.claims],
                            "evidence_urls": [cl.url for cl in c.claims],
                            "matched_must_have": c.matched_must_have,
                            "missing_must_have": c.missing_must_have,
                            "matched_nice_to_have": c.matched_nice_to_have} for c in found],
            "note": "Matched requirements are mentions in stored evidence, not verified proficiency. "
                    "Missing requirements mean no stored evidence was found, not that the student lacks the skill. "
                    "Do not infer seniority, availability or employment eligibility.",
            "sources": [{"title": f"{c.name}: evidence", "url": cl.url, "collection": "students"}
                        for c in found for cl in c.claims]}


class StudentArgs(BaseModel):
    student_id: str = Field(min_length=1, max_length=60, description="Student id from hiring_match")


@tool("shortlist_add", "Add a student to the recruiter's shortlist.", StudentArgs, blocking=False)
async def shortlist_add(ctx: ToolContext, a: StudentArgs) -> dict:
    v = await _visitor(ctx)
    if a.student_id.lower() not in await asyncio.to_thread(hiring.student_data):
        raise ToolError("That student is not in the opted-in list.")
    return {"shortlist": await asyncio.to_thread(ctx.get("memory").shortlist_add, v.id, a.student_id.lower())}


@tool("shortlist_remove", "Remove a student from the recruiter's shortlist.", StudentArgs, blocking=False)
async def shortlist_remove(ctx: ToolContext, a: StudentArgs) -> dict:
    v = await _visitor(ctx)
    return {"shortlist": await asyncio.to_thread(ctx.get("memory").shortlist_remove, v.id, a.student_id.lower())}


@tool("visit_summary", "Link to the visitor's shareable visit summary page.", NoArgs)
async def visit_summary(ctx: ToolContext, a: NoArgs) -> dict:
    v = await _visitor(ctx)
    return {"url": f"/visit/{v.code}"}
