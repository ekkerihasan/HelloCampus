"""Hand-curated posts (for example AITM's own LinkedIn posts), pasted by the team, never fetched automatically.
Each post keeps its public URL so the host cites it. Placeholder rows are validated but never indexed.
Validate: python -m backend.rag.posts"""
import json
import sys
from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field, TypeAdapter, ValidationError, field_validator

from backend.config import settings
from scraper.normalize import Record


class Post(BaseModel):
    id: str = Field(pattern=r"^post-\d{3}$")
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=6000)  # the post text as published, pasted by a team member
    posted_on: date | None = None
    source_url: str
    collection: str = Field(default="achievements", pattern=r"^(campus|achievements)$")
    last_checked: date
    placeholder: bool = False

    @field_validator("source_url")
    @classmethod
    def https_link(cls, v: str) -> str:
        if not v.startswith("https://"):
            raise ValueError("source_url must be the post's public https:// link")
        return v


_posts = TypeAdapter(list[Post])


def load(path: Path | None = None) -> list[Post]:
    path = path or settings.posts_path
    if not path.exists():
        return []
    return _posts.validate_python(json.loads(path.read_text(encoding="utf-8")))


def post_records(path: Path | None = None) -> dict[str, list[Record]]:
    out: dict[str, list[Record]] = {"campus": [], "achievements": []}
    for p in load(path):
        if p.placeholder:
            continue
        when = f" Posted on {p.posted_on.isoformat()}." if p.posted_on else ""
        out[p.collection].append(Record(id=f"{p.collection}-{p.id}", collection=p.collection, title=p.title,
                                        text=p.text + when, source_url=p.source_url,
                                        last_checked=p.last_checked.isoformat()))
    return out


if __name__ == "__main__":
    try:
        posts = load()
    except (ValidationError, json.JSONDecodeError) as exc:
        print(f"posts.json: INVALID\n{exc}")
        sys.exit(1)
    real = [p for p in posts if not p.placeholder]
    print(f"{len(posts)} posts, {len(real)} real, {len(posts) - len(real)} placeholders")
    print("posts.json: VALID")
