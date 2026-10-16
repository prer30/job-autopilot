"""SQLite application tracker: every job seen, and what you did with it."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from .models import Job

STATUSES = ("new", "applied", "skipped", "closed", "interviewing", "rejected", "offer")

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  dedupe_key TEXT,
  source TEXT, company TEXT, title TEXT, url TEXT,
  locations TEXT, category TEXT, level TEXT, terms TEXT, sponsorship TEXT,
  salary TEXT, tags TEXT,
  date_posted INTEGER, first_seen INTEGER, last_seen INTEGER,
  score REAL DEFAULT 0,
  status TEXT DEFAULT 'new',
  status_at INTEGER, resume TEXT, notes TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS jobs_dedupe ON jobs(dedupe_key);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status, score);
"""


class DB:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def upsert(self, job: Job, score: float) -> bool:
        """Insert a job; returns True if it's new. Cross-list duplicates are merged."""
        now = int(time.time())
        row = self.conn.execute("SELECT id FROM jobs WHERE id=?", (job.id,)).fetchone()
        if not row:
            row = self.conn.execute(
                "SELECT id FROM jobs WHERE dedupe_key=? AND company<>'' LIMIT 1", (job.dedupe_key,)).fetchone()
        if row:
            self.conn.execute("UPDATE jobs SET last_seen=?, score=MAX(score, ?) WHERE id=?",
                              (now, score, row["id"]))
            # Prefer the employer's own application link over an aggregator's redirect page.
            if "jobright.ai" not in job.url:
                self.conn.execute("UPDATE jobs SET url=? WHERE id=? AND url LIKE '%jobright.ai%'",
                                  (job.url, row["id"]))
            return False
        self.conn.execute(
            "INSERT INTO jobs (id, dedupe_key, source, company, title, url, locations, category, level, terms,"
            " sponsorship, salary, tags, date_posted, first_seen, last_seen, score) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (job.id, job.dedupe_key, job.source, job.company, job.title, job.url,
             json.dumps(job.locations), job.category, job.level, json.dumps(job.terms),
             job.sponsorship, job.salary, json.dumps(job.tags), job.date_posted, now, now, score))
        return True

    def commit(self) -> None:
        self.conn.commit()

    def queue(self, limit: int = 20, category: str | None = None, level: str | None = None) -> list[sqlite3.Row]:
        q, args = "SELECT * FROM jobs WHERE status='new'", []
        if category:
            q += " AND category=?"; args.append(category)
        if level:
            q += " AND level=?"; args.append(level)
        q += " ORDER BY score DESC, date_posted DESC LIMIT ?"
        args.append(limit)
        return self.conn.execute(q, args).fetchall()

    def get(self, job_id: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM jobs WHERE id=? OR id LIKE ?", (job_id, job_id + "%")).fetchone()

    def set_status(self, job_id: str, status: str, resume: str | None = None, note: str | None = None) -> None:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        self.conn.execute(
            "UPDATE jobs SET status=?, status_at=?, resume=COALESCE(?, resume),"
            " notes=CASE WHEN ? IS NULL THEN notes ELSE trim(notes || char(10) || ?) END WHERE id=?",
            (status, int(time.time()), resume, note, note, job_id))
        self.conn.commit()

    def by_status(self, status: str) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM jobs WHERE status=? ORDER BY status_at DESC", (status,)).fetchall()

    def counts(self) -> dict[str, int]:
        return {r[0]: r[1] for r in self.conn.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status")}

    def all_rows(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM jobs ORDER BY first_seen DESC").fetchall()
