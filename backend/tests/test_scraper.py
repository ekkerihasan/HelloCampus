"""T1.1: scrapers produce normalized records with source_url. Network tests write to tmp dirs only,
never into data/clean, and are skipped with HC_OFFLINE=1."""
import os
from pathlib import Path

import pytest

from scraper import scrape_github, scrape_web
from scraper.normalize import PoliteFetcher, read_jsonl

offline = pytest.mark.skipif(os.getenv("HC_OFFLINE") == "1", reason="offline run")


def test_optin_gate(tmp_path: Path) -> None:
    csv_path = tmp_path / "optin.csv"
    csv_path.write_text("name,github_username,headline,consent\nA,alpha,,yes\nB,beta,,no\nC,,,yes\n")
    assert scrape_github.optin_usernames(csv_path) == {"alpha"}


def test_blocked_hosts_skipped(tmp_path: Path) -> None:
    src = tmp_path / "sources.yaml"
    src.write_text("campus:\n  - https://www.linkedin.com/in/someone\nachievements: []\n")
    counts = scrape_web.scrape(src, tmp_path / "clean", PoliteFetcher(cache_dir=tmp_path / "raw", delay_s=0))
    assert counts["campus"] == 0


@offline
def test_web_scrape_real_page(tmp_path: Path) -> None:
    src = tmp_path / "sources.yaml"
    src.write_text("campus:\n  - https://en.wikipedia.org/wiki/Hackathon\nachievements: []\n")
    counts = scrape_web.scrape(src, tmp_path / "clean", PoliteFetcher(cache_dir=tmp_path / "raw"))
    recs = read_jsonl(tmp_path / "clean" / "campus.jsonl")
    assert counts["campus"] == 1 and recs[0].source_url.startswith("https://") and len(recs[0].text) > 200


@offline
def test_github_scrape_public_user(tmp_path: Path) -> None:
    csv_path = tmp_path / "optin.csv"
    csv_path.write_text("name,github_username,headline,consent\nThe Octocat,octocat,test only,yes\n")
    n = scrape_github.scrape(csv_path, tmp_path / "clean",
                             scrape_github.GitHub(PoliteFetcher(cache_dir=tmp_path / "raw", delay_s=0.2)))
    recs = read_jsonl(tmp_path / "clean" / "students.jsonl")
    assert n >= 2
    assert all(r.entity_id == "octocat" and r.source_url.startswith("https://github.com/") for r in recs)
    assert any(r.extra.get("kind") == "profile" for r in recs)
