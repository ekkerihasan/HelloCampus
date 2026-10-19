"""Builds the message list for a chat turn: persona, visitor facts, retrieved context, recent turns."""
import re

from backend.llm.characters import GROUNDING_RULES, SMALLTALK_RULES, Character
from backend.llm.client import ChatMessage
from backend.rag.store import Hit
from backend.config import settings

SMALLTALK = re.compile(
    r"^\s*(hi+|hello+|hey+|yo|good (morning|afternoon|evening)|thanks?( you)?|thank you|thx|ok(ay)?|cool|great|"
    r"nice|bye|see you|how are you|who are you|what can you do|what are you)\b[\s!.?,]*\w{0,12}[\s!.?]*$",
    re.IGNORECASE,
)

REFUSAL = ("I don't have that yet. The help desk or a student volunteer will know, "
           "and if you tell me more I can look again.")


def is_smalltalk(message: str) -> bool:
    # Full match prevents greetings followed by factual questions bypassing retrieval.
    return bool(re.fullmatch(
        r"\s*(hi+|hello+|hey+|yo|good (morning|afternoon|evening)|thanks?( you)?|"
        r"thank you|thx|ok(ay)?|cool|great|nice|bye|see you|how are you|who are you|"
        r"what can you do|what are you)[\s!.?,]*", message, re.IGNORECASE))


def excerpt(text: str, question: str, budget: int) -> str:
    """Select an original passage near question terms rather than cutting off relevant details."""
    if len(text) <= budget:
        return text
    terms = {w.lower() for w in re.findall(r"\w{3,}", question)} - {
        "what", "where", "when", "which", "does", "have", "about", "the", "can", "how", "aitm"}
    width = max(1, budget - 2)
    starts = {0, max(0, len(text) - width)}
    for term in terms:
        for match in re.finditer(rf"\b{re.escape(term)}\w*", text, re.IGNORECASE):
            starts.add(max(0, min(match.start() - width // 3, len(text) - width)))
    def score(start: int) -> tuple[int, int]:
        passage = text[start:start + width].lower()
        return sum(bool(re.search(rf"\b{re.escape(term)}\w*", passage)) for term in terms), -start
    best_start = max(sorted(starts), key=score)
    passage = text[best_start:best_start + width]
    return (("…" if best_start else "") + passage +
            ("…" if best_start + width < len(text) else ""))[:budget]


def context_block(hits: list[Hit], question: str = "") -> str:
    if not hits:
        return "CONTEXT: (empty)"
    per_hit = max(1, settings.chat_context_chars // len(hits))
    parts = [f"[{i}] {h.title} ({h.source_url})\n{excerpt(h.text, question, per_hit)}" for i, h in enumerate(hits, 1)]
    return "CONTEXT:\n" + "\n\n".join(parts)


def build_messages(char: Character, user_message: str, hits: list[Hit], visitor_block: str,
                   history: list[ChatMessage], smalltalk: bool) -> list[ChatMessage]:
    system = [char.persona, SMALLTALK_RULES if smalltalk else GROUNDING_RULES]
    if visitor_block:
        system.append(visitor_block)
    if not smalltalk:
        system.append(context_block(hits, user_message))
    # Storage retains ten messages, while prompts stay within the local model's context budget.
    recent, remaining = [], settings.chat_history_chars
    for message in reversed(history):
        if remaining <= 0:
            break
        content = message.content[-remaining:]
        recent.append(ChatMessage(role=message.role, content=content))
        remaining -= len(content)
    return [ChatMessage(role="system", content="\n\n".join(system)), *reversed(recent),
            ChatMessage(role="user", content=user_message)]
