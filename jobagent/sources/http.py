from __future__ import annotations

import requests

_SESSION = requests.Session()
_SESSION.headers["User-Agent"] = "job-autopilot/0.1 (+personal job search tool)"


def get_text(url: str, timeout: int = 30) -> str:
    r = _SESSION.get(url, timeout=timeout)
    r.raise_for_status()
    return r.text


def get_json(url: str, timeout: int = 30):
    r = _SESSION.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()
