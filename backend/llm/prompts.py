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


def context_block(hits: list[Hit]) -> str:
    if not hits:
        return "CONTEXT: (empty)"
    per_hit = max(1, settings.chat_context_chars // len(hits))
    parts = [f"[{i}] {h.title} ({h.source_url})\n{h.text[:per_hit]}" for i, h in enumerate(hits, 1)]
    return "CONTEXT:\n" + "\n\n".join(parts)


def build_messages(char: Character, user_message: str, hits: list[Hit], visitor_block: str,
                   history: list[ChatMessage], smalltalk: bool) -> list[ChatMessage]:
    system = [char.persona, SMALLTALK_RULES if smalltalk else GROUNDING_RULES]
    if visitor_block:
        system.append(visitor_block)
    if not smalltalk:
        system.append(context_block(hits))
    return [ChatMessage(role="system", content="\n\n".join(system)), *history,
            ChatMessage(role="user", content=user_message)]
