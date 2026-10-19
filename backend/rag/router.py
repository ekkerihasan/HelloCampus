"""Picks which collections to search with keyword rules. No match means all collections: hybrid search over a few
hundred local chunks costs nothing, while an LLM router would spend free-tier quota on every question."""
import re

COLLECTIONS = ("campus", "achievements", "students", "locality")

RULES: dict[str, tuple[str, ...]] = {
    "locality": ("eat", "food", "lunch", "dinner", "breakfast", "coffee", "chai", "snack", "restaurant", "cafe",
                 "veg", "bus", "train", "railway", "station", "airport", "auto", "cab", "taxi", "metro", "fare",
                 "atm", "pharmacy", "medical", "hotel", "stay", "hostel", "nearby", "around here", "travel"),
    "students": ("hire", "hiring", "intern", "candidate", "developer", "student", "github", "repo",
                 "portfolio", "frontend", "backend", "full stack", "ml engineer", "talent", "who built", "who knows"),
    "achievements": ("hackathon", "won", "winner", "award", "prize", "achievement", "competition", "rank",
                     "medal", "recognition", "best project", "proud", "champion", "title"),
    "campus": ("aitm", "anjuman", "campus", "college", "department", "club", "event", "session", "talk",
               "where is", "library", "lab", "fest", "course", "faculty", "history", "about", "hall", "block"),
}


def route(question: str) -> list[str]:
    q = question.lower()
    picked = [c for c, words in RULES.items() if any(re.search(rf"\b{re.escape(w)}", q) for w in words)]
    return picked or list(COLLECTIONS)
