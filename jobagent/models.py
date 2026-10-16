"""Core data types."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

# Query params that only track where a click came from; dropping them makes
# the same posting from two different lists dedupe to one URL.
_TRACKING = re.compile(r"^(utm_.*|ref|source|src|gh_src|lever-source.*|s|trk)$", re.I)


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _TRACKING.match(k)]
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower() or "https", parts.netloc.lower(), path, urlencode(query), ""))


def make_id(url: str, company: str = "", title: str = "") -> str:
    key = normalize_url(url) or f"{company}|{title}".lower()
    return hashlib.sha1(key.encode()).hexdigest()[:10]


@dataclass
class Job:
    source: str
    company: str
    title: str
    url: str
    locations: list[str] = field(default_factory=list)
    category: str = "other"        # swe | ml_data | pm | quant | hardware | other
    level: str = "unknown"         # intern | newgrad | unknown
    terms: list[str] = field(default_factory=list)
    sponsorship: str = ""          # free text from the source, if any
    date_posted: int = 0           # unix seconds, 0 if unknown
    salary: str = ""
    tags: list[str] = field(default_factory=list)   # e.g. "faang", "advanced-degree"
    id: str = ""

    def __post_init__(self) -> None:
        self.company = re.sub(r"\s+", " ", self.company or "").strip()
        self.title = re.sub(r"\s+", " ", self.title or "").strip()
        self.url = (self.url or "").strip()
        if not self.id:
            self.id = make_id(self.url, self.company, self.title)

    @property
    def dedupe_key(self) -> str:
        """Same company + same title + overlapping location = same job, across lists."""
        t = re.sub(r"[^a-z0-9]+", " ", self.title.lower()).strip()
        c = re.sub(r"[^a-z0-9]+", " ", self.company.lower()).strip()
        return f"{c}|{t}"

    def to_dict(self) -> dict:
        return asdict(self)
