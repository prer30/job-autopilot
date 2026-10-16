"""jobagent — find CS & PM roles, pre-fill applications, you click Submit."""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime

from rich.console import Console
from rich.table import Table

from . import config
from .db import DB, STATUSES

console = Console()


def _db() -> DB:
    return DB(config.DATA / "jobs.db")


def _age(ts: int) -> str:
    if not ts:
        return "?"
    d = (time.time() - ts) / 86400
    return f"{int(d * 24)}h" if d < 1 else f"{int(d)}d"


def cmd_init(a) -> None:
    created = config.init()
    for c in created:
        console.print(f"created [bold]{c}[/]")
    console.print("\nNext:\n  1. Fill in [bold]config/profile.yaml[/]\n  2. Put your resume PDF(s) in [bold]resumes/[/]"
                  "\n  3. Run [bold]jobagent fetch[/] then [bold]jobagent apply[/]")


def cmd_fetch(a) -> None:
    from .ranking import keep, score
    from .sources import fetch_all
    s = config.settings()
    search = s.get("search", {})
    with console.status("Pulling job lists…"):
        jobs, report = fetch_all(s.get("sources", []), s.get("watch_companies", []))
    for name, r in report.items():
        style = "red" if r.startswith("error") else "dim"
        console.print(f"  [{style}]{name}: {r[:140]}[/]")
    db = _db()
    kept = new = 0
    fresh = []
    for job in jobs:
        ok, _ = keep(job, search)
        if not ok:
            continue
        kept += 1
        if db.upsert(job, score(job, search)):
            new += 1
            fresh.append(job)
    db.commit()
    console.print(f"\n[bold]{len(jobs)}[/] listings → [bold]{kept}[/] match your filters → [bold green]{new} new[/]")
    if a.digest:
        _write_digest(fresh, a.digest)
        console.print(f"digest written to {a.digest}")


def _write_digest(jobs, path: str) -> None:
    from .ranking import score
    s = config.settings().get("search", {})
    jobs = sorted(jobs, key=lambda j: -score(j, s))
    lines = [f"# New matching roles — {datetime.now():%b %d, %Y}", "",
             f"{len(jobs)} new roles.", "", "| Company | Role | Level | Location | Link |", "|---|---|---|---|---|"]
    for j in jobs[:300]:
        loc = ", ".join(j.locations[:2])
        lines.append(f"| {j.company} | {j.title} | {j.level} | {loc} | [apply]({j.url}) |")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _table(rows, title: str) -> Table:
    t = Table(title=title, show_lines=False, header_style="bold")
    for col in ("id", "score", "company", "role", "type", "where", "age"):
        t.add_column(col, overflow="fold" if col == "role" else "ellipsis", max_width=None if col == "role" else 28)
    for r in rows:
        locs = json.loads(r["locations"] or "[]")
        t.add_row(r["id"][:7], f"{r['score']:.0f}", r["company"], r["title"], f"{r['category']}/{r['level']}",
                  ", ".join(locs[:2]), _age(r["date_posted"]))
    return t


def cmd_list(a) -> None:
    rows = _db().queue(a.limit, a.role, a.level)
    if not rows:
        console.print("Queue is empty — run [bold]jobagent fetch[/].")
        return
    console.print(_table(rows, "Your queue (best first)"))


def cmd_apply(a) -> None:
    from .apply.session import run
    db = _db()
    if a.ids:
        rows = [db.get(i) for i in a.ids]
        missing = [i for i, r in zip(a.ids, rows) if r is None]
        if missing:
            sys.exit(f"unknown job id(s): {', '.join(missing)}")
    else:
        rows = db.queue(a.n, a.role, a.level)
    if not rows:
        console.print("Nothing to apply to — run [bold]jobagent fetch[/] first.")
        return
    console.print(_table(rows, f"Applying to {len(rows)} job(s) — you click Submit on each"))
    run([dict(r) for r in rows], db, config.settings(), config.profile())


def cmd_mark(a) -> None:
    db = _db()
    row = db.get(a.id)
    if not row:
        sys.exit(f"unknown job id {a.id}")
    db.set_status(row["id"], a.status, note=a.note)
    console.print(f"{row['company']} — {row['title']} → [bold]{a.status}[/]")


def cmd_stats(a) -> None:
    db = _db()
    counts = db.counts()
    t = Table(title="Applications", header_style="bold")
    t.add_column("status"); t.add_column("count", justify="right")
    for s in STATUSES:
        t.add_row(s, str(counts.get(s, 0)))
    console.print(t)
    recent = db.by_status("applied")[:10]
    if recent:
        rt = Table(title="Recently applied", header_style="bold")
        for c in ("when", "company", "role", "resume"):
            rt.add_column(c)
        for r in recent:
            rt.add_row(datetime.fromtimestamp(r["status_at"]).strftime("%b %d"), r["company"], r["title"], r["resume"] or "")
        console.print(rt)


def cmd_export(a) -> None:
    rows = _db().all_rows()
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        cols = ["id", "status", "company", "title", "category", "level", "url", "locations", "date_posted",
                "status_at", "resume", "notes", "source"]
        w.writerow(cols)
        for r in rows:
            vals = [r[c] for c in cols]
            for i, c in enumerate(cols):
                if c in ("date_posted", "status_at") and vals[i]:
                    vals[i] = datetime.fromtimestamp(vals[i]).strftime("%Y-%m-%d")
            w.writerow(vals)
    console.print(f"exported {len(rows)} rows to {a.out}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="jobagent", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="create config files and folders").set_defaults(fn=cmd_init)

    f = sub.add_parser("fetch", help="pull new jobs from every source")
    f.add_argument("--digest", metavar="FILE", help="also write the new jobs to a markdown file")
    f.set_defaults(fn=cmd_fetch)

    for name, fn, helptext in (("list", cmd_list, "show your ranked queue"),
                               ("apply", cmd_apply, "open + pre-fill applications; you submit")):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("--role", choices=["swe", "ml_data", "pm", "quant", "hardware", "other"])
        sp.add_argument("--level", choices=["intern", "newgrad", "unknown"])
        if name == "list":
            sp.add_argument("--limit", type=int, default=25)
        else:
            sp.add_argument("-n", type=int, default=5, help="how many jobs this session (default 5)")
            sp.add_argument("ids", nargs="*", help="specific job ids from `jobagent list`")
        sp.set_defaults(fn=fn)

    m = sub.add_parser("mark", help="update a job's status (e.g. interviewing)")
    m.add_argument("id"); m.add_argument("status", choices=STATUSES); m.add_argument("--note")
    m.set_defaults(fn=cmd_mark)

    sub.add_parser("stats", help="how many applied / skipped / interviewing").set_defaults(fn=cmd_stats)
    e = sub.add_parser("export", help="export your tracker to CSV")
    e.add_argument("--out", default="applications.csv")
    e.set_defaults(fn=cmd_export)

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
