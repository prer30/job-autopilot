"""Filter jobs down to the ones you'd actually apply to, then rank them."""
from __future__ import annotations

import re
import time
from functools import lru_cache

from .classify import is_senior
from .models import Job

@lru_cache(maxsize=32)
def _place_rx(places: tuple[str, ...]) -> re.Pattern | None:
    """Whole-word match so 'TX' doesn't hit 'Netx' and 'SF' doesn't hit 'Transfer'."""
    places = tuple(p.strip() for p in places if p and p.strip())
    if not places:
        return None
    return re.compile(r"(?<![A-Za-z])(" + "|".join(re.escape(p) for p in places) + r")(?![A-Za-z])", re.I)


def in_places(locations: list[str], places) -> bool:
    rx = _place_rx(tuple(places or ()))
    return bool(rx and rx.search(" | ".join(locations)))


_NO_SPONSOR = ("does not offer sponsorship", "citizenship is required", "u.s. citizen")


def keep(job: Job, s: dict, now: float | None = None) -> tuple[bool, str]:
    now = now or time.time()
    title = job.title.lower()
    if job.category not in s.get("roles", ["swe", "ml_data", "pm"]):
        return False, f"category {job.category}"
    if job.level not in s.get("levels", ["intern", "newgrad", "unknown"]):
        return False, f"level {job.level}"
    if is_senior(job.title):
        return False, "senior title"
    for kw in s.get("exclude_title_keywords", []):
        if kw.lower() in title:
            return False, f"keyword {kw}"
    if any(c.lower() == job.company.lower() for c in s.get("exclude_companies", [])):
        return False, "excluded company"
    max_age = s.get("max_age_days", 0)
    if max_age and job.date_posted and now - job.date_posted > max_age * 86400:
        return False, "too old"
    if s.get("needs_sponsorship") and any(x in job.sponsorship.lower() for x in _NO_SPONSOR):
        return False, "no sponsorship"
    if s.get("skip_advanced_degree_only") and "advanced-degree" in job.tags:
        return False, "advanced degree only"
    locs = " | ".join(job.locations).lower()
    if locs and s.get("countries_exclude"):
        parts = [p.strip() for p in locs.split("|")]
        if parts and all(any(c.lower() in p for c in s["countries_exclude"]) for p in parts):
            return False, "country"
    if s.get("locations") and locs:
        remote_ok = s.get("include_remote", True) and "remote" in locs
        if not remote_ok and not in_places(job.locations, s["locations"]):
            return False, "location"
    return True, ""


def score(job: Job, s: dict, now: float | None = None) -> float:
    now = now or time.time()
    pts = 0.0
    if job.date_posted:
        age_days = max(0.0, (now - job.date_posted) / 86400)
        pts += max(0.0, 40 - 2 * age_days)          # fresh postings matter most
    else:
        pts += 10
    dream = [d.lower() for d in s.get("dream_companies", [])]
    if job.company.lower() in dream:
        pts += 30
    if "faang" in job.tags:
        pts += 10
    if in_places(job.locations, s.get("preferred_locations")):
        pts += 20                                   # your preferred cities rank first
    elif in_places(job.locations, s.get("locations")):
        pts += 10
    if job.source in ("greenhouse", "lever", "ashby"):
        pts += 5                                    # straight from the company = newest
    return round(pts, 1)
