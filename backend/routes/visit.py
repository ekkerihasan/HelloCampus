"""GET /visit/{code}: mobile-friendly, shareable visit summary (ADDENDUM-01 section 9.4). Server-rendered so it
opens on any device from the code alone. Shows only stored data; every link comes from stored records."""
import asyncio
from html import escape

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from backend.hiring import service as hiring
from backend.routes.deps import optional, require

router = APIRouter()

STYLE = """
:root{--bg:#fbfaf7;--fg:#1d1d1b;--muted:#5f5d57;--card:#fff;--line:#e6e2da;--accent:#2f6d5a}
@media (prefers-color-scheme:dark){:root{--bg:#161614;--fg:#eceae4;--muted:#a9a59b;--card:#1f1f1c;--line:#34332f;--accent:#7cc4a9}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}
main{max-width:640px;margin:0 auto;padding:24px 16px 48px}h1{font-size:1.6rem;margin:0 0 4px}
h2{font-size:1.05rem;margin:28px 0 8px}.muted{color:var(--muted)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin:8px 0}
a{color:var(--accent);overflow-wrap:anywhere}ul{padding-left:20px;margin:4px 0}.code{font-family:ui-monospace,monospace;
letter-spacing:.15em;font-weight:700}
"""


def _section(title: str, body: str) -> str:
    return f"<h2>{escape(title)}</h2>{body}"


@router.get("/visit/{code}", response_class=HTMLResponse)
async def visit(code: str, mem=Depends(require("memory")), sched=Depends(optional("schedule"))) -> str:
    v = await asyncio.to_thread(mem.by_code, code)
    if v is None:
        raise HTTPException(404, "No visit with that code.")
    parts = [f"<h1>Hello, {escape(v.name)}</h1>",
             f"<p class=muted>Your visit code is <span class=code>{escape(v.code)}</span>. "
             "Enter it on any device to pick up where you left off.</p>"]
    if v.purpose or v.summary:
        parts.append(_section("Your visit", f"<div class=card>{escape(v.purpose)}"
                                            f"{'<br>' if v.purpose and v.summary else ''}{escape(v.summary)}</div>"))
    facts = [(k, val) for k, val in v.facts.items() if val]
    if facts:
        items = "".join(f"<li><b>{escape(k.replace('_', ' ').capitalize())}:</b> "
                        f"{escape(', '.join(map(str, val)) if isinstance(val, list) else str(val))}</li>"
                        for k, val in facts)
        parts.append(_section("What you asked about", f"<ul>{items}</ul>"))
    if sched is not None:
        events = await asyncio.to_thread(sched.upcoming, None, 5)
        if events:
            rows = "".join(f"<div class=card><b>{escape(e['title'])}</b><br><span class=muted>"
                           f"{escape(e['date'])} {escape(e['start_time'])} {escape(e['venue'])}</span></div>"
                           for e in events)
            parts.append(_section("Coming up", rows))
        veg = any("veg" in str(p).lower() for p in v.facts.get("preferences", []))
        food = await asyncio.to_thread(sched.local, "food", True if veg else None, 4)
        if food:
            rows = "".join(f"<div class=card><b>{escape(f['name'])}</b><br><span class=muted>"
                           f"{escape(f.get('what_to_order', ''))} {escape(f.get('price_range', ''))} "
                           f"{escape(f.get('distance_from_campus', ''))}</span></div>" for f in food)
            parts.append(_section("Places to eat" + (" (vegetarian)" if veg else ""), rows))
    if v.shortlist:
        data = await asyncio.to_thread(hiring.student_data)
        rows = []
        for key in v.shortlist:
            if key not in data:
                continue
            c = hiring.candidate(key, data[key])
            links = "".join(f"<li><a href='{escape(u)}' rel=noopener target=_blank>{escape(u)}</a></li>"
                            for u in c.sources[:5])
            rows.append(f"<div class=card><b>{escape(c.name)}</b> <span class=muted>@{escape(c.entity_id)}</span>"
                        f"<br>{escape(c.headline)}<ul>{links}</ul></div>")
        if rows:
            parts.append(_section("Your shortlist", "".join(rows)))
    return (f"<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content='width=device-width,"
            f"initial-scale=1'><title>Your visit</title><style>{STYLE}</style><main>{''.join(parts)}"
            f"<p class=muted>Hello Campus</p></main></html>")
