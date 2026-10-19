"""Guide and Analyst: same retrieved context, different tone and temperature (BUILD.md 4.2)."""
from enum import Enum

from pydantic import BaseModel

from backend.config import settings


class CharacterName(str, Enum):
    guide = "guide"
    analyst = "analyst"


class Character(BaseModel):
    name: CharacterName
    label: str
    temperature: float
    persona: str


CHARACTERS: dict[CharacterName, Character] = {
    CharacterName.guide: Character(
        name=CharacterName.guide, label="Guide", temperature=settings.temp_guide,
        persona=(
            "You are the Guide at Hello Campus: a warm, upbeat local who loves this campus and its people. "
            "Talk like a friend showing someone around. Short sentences, a little personality, no lists unless asked. "
            "Keep answers to 2 to 4 sentences unless the visitor asks for more."
        ),
    ),
    CharacterName.analyst: Character(
        name=CharacterName.analyst, label="Analyst", temperature=settings.temp_analyst,
        persona=(
            "You are the Analyst at Hello Campus: a precise, calm colleague. Lead with the exact answer, "
            "then any key detail (times, places, contacts). Use short bullet points when there are several facts. "
            "No small talk, no exclamation marks."
        ),
    ),
}

def character(name: CharacterName | str) -> Character:
    return CHARACTERS[CharacterName(name)]
