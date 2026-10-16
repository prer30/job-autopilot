"""Parser for job lists published as markdown/HTML tables in a GitHub README
(SpeedyApply, Jobright, vanshb03-style new-grad lists, ...).

Works off the header row, so new repos with slightly different columns usually
just work: it looks for company / role / location / link / age-or-date columns.
"""
from __future__ import annotations

import html
import re
import time
from datetime import datetime

from ..classify import classify_category, classify_level
from ..models import Job
from .http import get_text

_HREF = re.compile(r'href="([^"]+)"|\]\((https?://[^)\s]+)\)')
_TAG = re.compile(r"<[^>]+>")
_MDLINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")

COLS = {
    "company": ("company",),
    "title": ("position", "role", "job title", "title"),
    "location": ("location",),
    "link": ("posting", "application", "apply", "link"),
    "age": ("age", "date posted", "posted", "date"),
    "salary": ("salary", "pay", "compensation"),
}


def _cells(line: str) -> list[str]:
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    return [c.strip() for c in inner.split("|")]


def _text(cell: str) -> str:
    cell = re.sub(r"<br\s*/?>|</br>", " / ", cell, flags=re.I)
    cell = _MDLINK.sub(r"\1", cell)
    cell = _TAG.sub("", cell)
    cell = cell.replace("**", "").replace("__", "")
    return html.unescape(re.sub(r"\s+", " ", cell)).strip(" /")


def _links(cell: str) -> list[str]:
    return [a or b for a, b in _HREF.findall(cell)]


def _age_to_epoch(raw: str, now: float) -> int:
    raw = raw.strip().lower()
    m = re.match(r"^(\d+)\s*(d|day|days|w|wk|weeks?|mo|months?|h|hrs?|hours?)$", raw)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        days = n * (7 if unit.startswith("w") else 30 if unit.startswith("mo") else (1 / 24 if unit.startswith("h") else 1))
        return int(now - days * 86400)
    today = datetime.fromtimestamp(now)
    for fmt, yearless in (("%b %d", True), ("%B %d", True), ("%m/%d", True), ("%Y-%m-%d", False), ("%m/%d/%Y", False)):
        try:
            if yearless:  # "Oct 15" -> this year, or last year if that would be in the future
                dt = datetime.strptime(f"{raw.title()} {today.year}", fmt + " %Y")
                if dt > today:
                    dt = dt.replace(year=today.year - 1)
            else:
                dt = datetime.strptime(raw, fmt)
        except ValueError:
            continue
        return int(dt.timestamp())
    return 0


def _level_from_heading(heading: str) -> str:
    h = heading.lower()
    if "intern" in h or "co-op" in h:
        return "intern"
    if "new grad" in h or "new-grad" in h or "entry" in h:
        return "newgrad"
    return ""


def parse_tables(md: str, source: str, default_level: str = "", now: float | None = None) -> list[Job]:
    now = now or time.time()
    jobs: list[Job] = []
    heading = ""
    cols: dict[str, int] | None = None
    last_company = ""
    faang = False
    lines = md.splitlines()
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("#"):
            text = s.lstrip("#").strip()
            faang = "faang" in text.lower()
            lvl = _level_from_heading(text)
            if lvl or not heading:
                heading = text
            cols = None
            continue
        if not s.startswith("|"):
            if s:
                cols = None if not s.startswith("<") else cols
            continue
        cells = _cells(s)
        if all(re.fullmatch(r":?-{2,}:?", c or "--") for c in cells):
            continue  # separator row
        lower = [_text(c).lower() for c in cells]
        if any(c in ("company",) for c in lower) and len(cells) >= 3:
            cols = {}
            for key, names in COLS.items():
                for idx, name in enumerate(lower):
                    if any(name == n or name.startswith(n) for n in names) and key not in cols:
                        cols[key] = idx
            continue
        if not cols or "title" not in cols:
            continue
        row = cells + [""] * (max(cols.values()) + 1 - len(cells))
        raw_company = row[cols.get("company", 0)]
        company = _text(raw_company)
        if company in ("↳", "") and last_company:
            company = last_company
        last_company = company
        title_cell = row[cols["title"]]
        title = _text(title_cell)
        link_cell = row[cols["link"]] if "link" in cols else ""
        if "🔒" in s or "closed" in _text(link_cell).lower():
            continue
        urls = _links(link_cell) or _links(title_cell)
        if not urls or not title:
            continue
        loc = _text(row[cols["location"]]) if "location" in cols else ""
        level = _level_from_heading(heading) or default_level
        jobs.append(Job(
            source=source,
            company=company.replace("🔥", "").strip(),
            title=title,
            url=urls[0],
            locations=[p.strip() for p in re.split(r"\s*/\s*|;", loc) if p.strip()],
            category=classify_category(title),
            level=classify_level(title, level),
            date_posted=_age_to_epoch(_text(row[cols["age"]]), now) if "age" in cols else 0,
            salary=_text(row[cols["salary"]]) if "salary" in cols else "",
            tags=["faang"] if (faang or "🔥" in raw_company) else [],
        ))
    return jobs


def fetch_markdown(url: str, name: str, level: str = "") -> list[Job]:
    return parse_tables(get_text(url), source=name, default_level=level)
