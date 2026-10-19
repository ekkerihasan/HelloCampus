"""Public GitHub data for opt-in students only. Run: python -m scraper.scrape_github

Writes data/clean/students.jsonl: one profile record plus one record per top repo, all with entity_id = username.
"""
import base64
import csv
import json
import logging
from pathlib import Path

from pydantic import BaseModel

from backend.config import settings
from scraper.normalize import PoliteFetcher, Record, record_id, today, write_jsonl

log = logging.getLogger("hello_campus.scraper.github")
API = "https://api.github.com"
TOP_REPOS = 6
README_CHARS = 2500


class OptinStudent(BaseModel):
    name: str
    github_username: str
    headline: str = ""


def load_optin(path: Path | None = None) -> list[OptinStudent]:
    """Rows count only with consent = yes. This is the single gate for which students exist anywhere."""
    path = path or settings.students_optin_path
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    out = []
    for row in rows:
        if (row.get("consent") or "").strip().lower() not in ("yes", "y", "true", "1"):
            continue
        user = (row.get("github_username") or "").strip().lstrip("@")
        if user:
            out.append(OptinStudent(name=(row.get("name") or user).strip(), github_username=user,
                                    headline=(row.get("headline") or "").strip()))
    return out


def optin_usernames(path: Path | None = None) -> set[str]:
    return {s.github_username.lower() for s in load_optin(path)}


class GitHub:
    def __init__(self, fetcher: PoliteFetcher | None = None) -> None:
        headers = {"Accept": "application/vnd.github+json"}
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"
        self.fetcher = fetcher or PoliteFetcher(headers=headers)

    def json(self, path: str) -> dict | list | None:
        text = self.fetcher.get(API + path, check_robots=False)
        return json.loads(text) if text else None

    def readme(self, owner: str, repo: str) -> str:
        data = self.json(f"/repos/{owner}/{repo}/readme")
        if not isinstance(data, dict) or "content" not in data:
            return ""
        return base64.b64decode(data["content"]).decode("utf-8", errors="replace")


def student_records(student: OptinStudent, gh: GitHub) -> list[Record]:
    u = student.github_username
    profile = gh.json(f"/users/{u}")
    if not isinstance(profile, dict) or "login" not in profile:
        log.warning("no GitHub profile for %s", u)
        return []
    repos = gh.json(f"/users/{u}/repos?per_page=100&sort=pushed") or []
    own = [r for r in repos if isinstance(r, dict) and not r.get("fork")]
    own.sort(key=lambda r: (r.get("stargazers_count", 0), r.get("pushed_at") or ""), reverse=True)
    top = own[:TOP_REPOS]

    languages: dict[str, int] = {}
    repo_infos = []
    records = []
    for r in top:
        langs = gh.json(f"/repos/{u}/{r['name']}/languages") or {}
        for k, v in (langs.items() if isinstance(langs, dict) else []):
            languages[k] = languages.get(k, 0) + v
        readme = gh.readme(u, r["name"])[:README_CHARS]
        info = {
            "name": r["name"], "url": r["html_url"], "description": r.get("description") or "",
            "language": r.get("language") or "", "stars": r.get("stargazers_count", 0),
            "topics": r.get("topics", []), "pushed_at": r.get("pushed_at", ""),
            "homepage": r.get("homepage") or "",
        }
        repo_infos.append(info)
        text = (f"Repository {r['name']} by {student.name} (@{u}).\n"
                f"Description: {info['description']}\nMain language: {info['language']}. "
                f"Languages: {', '.join(langs) if isinstance(langs, dict) else ''}.\n"
                f"Topics: {', '.join(info['topics'])}. Stars: {info['stars']}. Last push: {info['pushed_at'][:10]}.\n"
                f"README excerpt:\n{readme}")
        records.append(Record(id=record_id("students", info["url"]), collection="students",
                              title=f"{student.name}: {r['name']}", text=text, source_url=info["url"],
                              last_checked=today(), entity_id=u, extra={"kind": "repo", "repo": info}))

    profile_readme = gh.readme(u, u)
    top_langs = [k for k, _ in sorted(languages.items(), key=lambda kv: -kv[1])][:6]
    summary = (f"{student.name} (@{u}) on GitHub. {student.headline}\n"
               f"Bio: {profile.get('bio') or ''}\nLocation: {profile.get('location') or ''}\n"
               f"Public repos: {profile.get('public_repos', 0)}. Followers: {profile.get('followers', 0)}.\n"
               f"Top languages: {', '.join(top_langs)}.\n"
               "Top projects: " + "; ".join(f"{i['name']} ({i['language']}): {i['description']}" for i in repo_infos))
    records.append(Record(
        id=record_id("students", profile["html_url"]), collection="students", title=f"{student.name} profile",
        text=summary, source_url=profile["html_url"], last_checked=today(), entity_id=u,
        extra={"kind": "profile", "name": student.name, "headline": student.headline, "bio": profile.get("bio") or "",
               "avatar_url": profile.get("avatar_url", ""), "top_languages": top_langs, "repos": repo_infos,
               "profile_readme": profile_readme, "blog": profile.get("blog") or ""},
    ))
    return records


def scrape(optin_path: Path | None = None, out_dir: Path | None = None, gh: GitHub | None = None) -> int:
    gh = gh or GitHub()
    records: list[Record] = []
    for s in load_optin(optin_path):
        records.extend(student_records(s, gh))
    if records:
        write_jsonl(records, (out_dir or settings.clean_dir) / "students.jsonl")
    return len(records)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print({"students": scrape()})
