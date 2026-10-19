"""Schema and validator for data/locality.json. Run: python -m backend.rag.locality

Placeholder entries ("placeholder": true) pass validation but are never ingested, so the app
refuses locality questions until the team adds real values.
"""
import json
import sys
from datetime import date
from pathlib import Path
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter, ValidationError, field_validator

from backend.config import settings

STALE_DAYS = 120


class _Base(BaseModel):
    id: str = Field(pattern=r"^(food|travel|place|practical)-\d{3}$")
    name: str = Field(min_length=1)
    distance_from_campus: str = ""
    address: str = ""
    notes: str = ""
    last_checked: date
    placeholder: bool = False
    source_url: str = "curated"  # a public link (e.g. OpenStreetMap) the host can cite, or "curated"

    @field_validator("source_url")
    @classmethod
    def real_link(cls, v: str) -> str:
        if v != "curated" and not v.startswith("https://"):
            raise ValueError('source_url must be an https:// link or "curated"')
        return v

    @field_validator("last_checked")
    @classmethod
    def not_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("last_checked is in the future")
        return v


class Food(_Base):
    type: Literal["food"]
    cuisine: str = ""
    what_to_order: str = ""
    price_range: str = ""
    veg_options: bool | None = None  # None means not confirmed: never stored or spoken as "no veg"
    timings: str = ""


class Travel(_Base):
    type: Literal["travel"]
    how_to_get_there: str = ""
    fare: str = ""
    duration: str = ""


class Place(_Base):
    type: Literal["place"]
    why_visit: str = ""
    timings: str = ""


class Practical(_Base):
    type: Literal["practical"]
    what: str = ""
    timings: str = ""


LocalityEntry = Annotated[Union[Food, Travel, Place, Practical], Field(discriminator="type")]
_adapter = TypeAdapter(list[LocalityEntry])


def load(path: Path | None = None) -> list[LocalityEntry]:
    path = path or settings.locality_path
    return _adapter.validate_python(json.loads(path.read_text(encoding="utf-8")))


def entry_text(e: LocalityEntry) -> str:
    """One chunk per entry (BUILD.md 4.3)."""
    skip = {"id", "placeholder", "last_checked", "source_url"}
    parts = [f"{k.replace('_', ' ')}: {v}" for k, v in e.model_dump().items() if k not in skip and v not in ("", None)]
    if getattr(e, "type", "") == "food" and getattr(e, "veg_options", None) is None:
        parts.append("veg options: not confirmed")
    return f"{e.name} ({e.type}). " + ". ".join(parts) + f". Last checked {e.last_checked.isoformat()}."


def validate(path: Path | None = None) -> tuple[bool, list[str]]:
    msgs: list[str] = []
    try:
        entries = load(path)
    except (ValidationError, json.JSONDecodeError, FileNotFoundError) as exc:
        return False, [str(exc)]
    ids = [e.id for e in entries]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        return False, [f"duplicate ids: {sorted(dupes)}"]
    real = [e for e in entries if not e.placeholder]
    placeholders = [e.id for e in entries if e.placeholder]
    stale = [e.id for e in real if (date.today() - e.last_checked).days > STALE_DAYS]
    by_type = {t: sum(1 for e in real if e.type == t) for t in ("food", "travel", "place", "practical")}
    msgs.append(f"{len(entries)} entries, {len(real)} real, {len(placeholders)} placeholders. Real by type: {by_type}")
    if placeholders:
        msgs.append(f"placeholders still to fill (not ingested): {', '.join(placeholders)}")
    if stale:
        msgs.append(f"warning: older than {STALE_DAYS} days, re-check: {', '.join(stale)}")
    if len(real) < 20:
        msgs.append(f"warning: BUILD.md asks for 20 to 30 real entries, have {len(real)}")
    return True, msgs


if __name__ == "__main__":
    ok, messages = validate()
    print("\n".join(messages))
    print("locality.json: VALID" if ok else "locality.json: INVALID")
    sys.exit(0 if ok else 1)
