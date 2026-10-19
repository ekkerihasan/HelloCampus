"""Rank curated places without a provider call or invented prices/distances."""
import re

from backend.rag.bm25 import BM25


def vegetarian_request(text: str) -> bool:
    """Recognize explicit positive requests without treating 'non-veg' as vegetarian."""
    text = re.sub(r"\bnon[\s-]*(?:veg(?:etarian)?|vegetarian)\b", "", text, flags=re.I)
    text = re.sub(r"\b(?:not|no)\s+(?:veg|vegetarian)\b", "", text, flags=re.I)
    return bool(re.search(r"\b(?:veg|vegetarian)\b", text, re.I))


def rank_places(items: list[dict], query: str) -> list[dict]:
    """Rank the entire eligible set first; stable alphabetical ties preserve predictable results.

    Search descriptive fields only: IDs, source links and verification dates are not preferences.
    A low keyword match never turns an unknown price, diet or opening time into a confirmed fact.
    """
    fields = ("name", "cuisine", "address", "what_to_order", "notes", "why_visit", "what",
              "how_to_get_there")
    ordered = sorted(items, key=lambda item: (item["name"].casefold(), item["id"]))
    index = BM25([item["id"] for item in ordered],
                 [" ".join(str(item.get(field) or "") for field in fields) for item in ordered])
    scores = {key: score for key, score, _ in index.search(query, len(ordered))}
    return sorted(ordered, key=lambda item: -scores.get(item["id"], 0.0))
