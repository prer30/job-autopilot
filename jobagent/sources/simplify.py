"""SimplifyJobs publishes its lists as structured JSON - far more reliable than scraping the README."""
from __future__ import annotations

from ..classify import classify_category, classify_level
from ..models import Job
from .http import get_json


def fetch_simplify(url: str, level: str, name: str = "simplify") -> list[Job]:
    data = get_json(url)
    jobs: list[Job] = []
    for row in data:
        if not row.get("active", True) or not row.get("is_visible", True):
            continue
        title = row.get("title", "")
        degrees = [d.lower() for d in row.get("degrees") or []]
        tags = []
        if degrees and all(("master" in d or "phd" in d or "mba" in d) for d in degrees):
            tags.append("advanced-degree")
        jobs.append(Job(
            source=name,
            company=row.get("company_name", ""),
            title=title,
            url=row.get("url", ""),
            locations=row.get("locations") or [],
            category=classify_category(title, row.get("category", "")),
            level=classify_level(title, level),
            terms=row.get("terms") or [],
            sponsorship=row.get("sponsorship", "") if row.get("sponsorship") != "Other" else "",
            date_posted=int(row.get("date_posted") or row.get("date_updated") or 0),
            tags=tags,
        ))
    return jobs
