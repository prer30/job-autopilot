"""Pull every configured source and return one flat list of jobs."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from ..models import Job
from .ats_boards import FETCHERS as ATS_FETCHERS
from .markdown_table import fetch_markdown
from .simplify import fetch_simplify


def _run(src: dict) -> tuple[str, list[Job] | Exception]:
    name = src.get("name") or src.get("type")
    try:
        kind = src["type"]
        if kind == "simplify_json":
            return name, fetch_simplify(src["url"], src.get("level", ""), name)
        if kind == "markdown":
            return name, fetch_markdown(src["url"], name, src.get("level", ""))
        if kind in ATS_FETCHERS:
            return name, ATS_FETCHERS[kind](src["token"], src.get("company") or src["token"])
        raise ValueError(f"unknown source type {kind!r}")
    except Exception as e:  # one dead source must never kill the whole fetch
        return name, e


def fetch_all(sources: list[dict], watch_companies: list[dict] | None = None):
    """Returns (jobs, report) where report maps source name -> count or error string."""
    todo = [s for s in sources if s.get("enabled", True)]
    for c in watch_companies or []:
        todo.append({"type": c["ats"], "token": c["token"], "company": c.get("name") or c["token"],
                     "name": f"{c['ats']}:{c.get('name') or c['token']}"})
    jobs: list[Job] = []
    report: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for name, result in pool.map(_run, todo):
            if isinstance(result, Exception):
                report[name] = f"error: {result}"
            else:
                report[name] = str(len(result))
                jobs.extend(result)
    return jobs, report
