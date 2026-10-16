"""Watch specific companies directly through their public ATS job-board APIs.

Lists like Simplify lag a few hours behind; hitting Greenhouse / Lever / Ashby
directly for your dream companies catches postings the moment they go live.
All three APIs are public, documented, and need no key.
"""
from __future__ import annotations

from datetime import datetime

from ..classify import classify_category, classify_level
from ..models import Job
from .http import get_json


def _iso(ts: str) -> int:
    try:
        return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp())
    except Exception:
        return 0


def _job(source, company, title, url, locs, posted) -> Job | None:
    level = classify_level(title)
    if level not in ("intern", "newgrad"):
        return None  # company boards are mostly experienced roles; keep early-career only
    return Job(source=source, company=company, title=title, url=url, locations=locs,
               category=classify_category(title), level=level, date_posted=posted)


def fetch_greenhouse(token: str, company: str) -> list[Job]:
    data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs")
    out = []
    for j in data.get("jobs", []):
        job = _job("greenhouse", company, j.get("title", ""), j.get("absolute_url", ""),
                   [j.get("location", {}).get("name", "")], _iso(j.get("first_published") or j.get("updated_at", "")))
        if job:
            out.append(job)
    return out


def fetch_lever(token: str, company: str) -> list[Job]:
    data = get_json(f"https://api.lever.co/v0/postings/{token}?mode=json")
    out = []
    for j in data:
        cats = j.get("categories", {}) or {}
        job = _job("lever", company, j.get("text", ""), j.get("hostedUrl", ""),
                   cats.get("allLocations") or [cats.get("location", "")], int((j.get("createdAt") or 0) / 1000))
        if job:
            out.append(job)
    return out


def fetch_ashby(token: str, company: str) -> list[Job]:
    data = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{token}")
    out = []
    for j in data.get("jobs", []):
        if not j.get("isListed", True):
            continue
        job = _job("ashby", company, j.get("title", ""), j.get("jobUrl", ""),
                   [j.get("location", "")], _iso(j.get("publishedAt", "")))
        if job:
            out.append(job)
    return out


FETCHERS = {"greenhouse": fetch_greenhouse, "lever": fetch_lever, "ashby": fetch_ashby}
