"""Picks which collections to search. Keyword rules first, LLM at temperature 0 as fallback."""
import logging
import re

from backend.llm.client import ChatMessage, OllamaClient
from backend.rag.store import COLLECTIONS

log = logging.getLogger("hello_campus.router")

RULES: dict[str, tuple[str, ...]] = {
    "locality": ("eat", "food", "lunch", "dinner", "breakfast", "coffee", "chai", "snack", "restaurant", "cafe",
                 "veg", "bus", "train", "railway", "station", "airport", "auto", "cab", "taxi", "metro", "fare",
                 "atm", "pharmacy", "medical", "hotel", "stay", "hostel", "nearby", "around here", "visit", "travel"),
    "students": ("hire", "hiring", "intern", "candidate", "developer", "engineer", "student", "github", "repo",
                 "portfolio", "frontend", "backend", "full stack", "ml engineer", "talent", "who built", "who knows"),
    "achievements": ("hackathon", "won", "winner", "award", "prize", "achievement", "competition", "rank",
                     "medal", "recognition", "best project", "proud"),
    "campus": ("campus", "college", "department", "club", "event", "session", "talk", "schedule", "timing",
               "when", "where is", "library", "lab", "contact", "fest", "course", "faculty", "history", "about"),
}


def route_rules(question: str) -> list[str]:
    q = question.lower()
    hits = [c for c, words in RULES.items() if any(re.search(rf"\b{re.escape(w)}", q) for w in words)]
    return hits


async def route(question: str, llm: OllamaClient | None = None) -> list[str]:
    cols = route_rules(question)
    if cols:
        return cols
    if llm is not None:
        prompt = (
            "Pick which knowledge collections can answer the visitor's question. Collections: "
            "campus (college info, events, clubs, timings, contacts), achievements (wins, awards, hackathons), "
            "students (opt-in student developers and their GitHub projects), locality (food, travel, places, practical "
            'needs near campus). Reply as JSON {"collections": [...]} using only those names.\n'
            f"Question: {question}"
        )
        data = await llm.chat_json([ChatMessage(role="user", content=prompt)])
        picked = [c for c in data.get("collections", []) if c in COLLECTIONS]
        if picked:
            log.info("llm router picked %s", picked)
            return picked
    return list(COLLECTIONS)
