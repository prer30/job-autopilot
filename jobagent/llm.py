"""Optional: ask Claude to draft answers for questions the rules don't cover.
Uses the plain HTTP API so there's no extra dependency. Set ANTHROPIC_API_KEY."""
from __future__ import annotations

import os

import requests

API = "https://api.anthropic.com/v1/messages"

SYSTEM = (
    "You help a job seeker fill out an application. Answer in first person, as the applicant, "
    "using ONLY facts in their profile and resume. Never invent experience, employers, numbers, "
    "or credentials. If the facts needed aren't there, reply exactly: SKIP. "
    "Keep free-text answers concise (2-5 sentences unless the question asks for more). "
    "For multiple-choice questions, reply with the exact text of one option and nothing else."
)


class Drafter:
    def __init__(self, model: str, profile: dict, resume_text: str = ""):
        self.key = os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model
        self.profile = profile
        self.resume_text = resume_text[:12000]

    @property
    def available(self) -> bool:
        return bool(self.key)

    def _context(self, job: dict) -> str:
        p = {k: v for k, v in self.profile.items() if k not in ("eeo", "custom_answers", "resumes")}
        return (f"Job: {job.get('title')} at {job.get('company')}\n\n"
                f"Applicant profile (YAML-ish): {p}\n\nResume text:\n{self.resume_text or '(not provided)'}")

    def ask(self, job: dict, question: str, options: list[str] | None = None, max_tokens: int = 400) -> str:
        if not self.available:
            return ""
        q = f"Question on the form: {question}"
        if options:
            q += "\nOptions:\n" + "\n".join(f"- {o}" for o in options if o)
        try:
            r = requests.post(API, timeout=60, headers={
                "x-api-key": self.key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": self.model, "max_tokens": max_tokens, "system": SYSTEM,
                      "messages": [{"role": "user", "content": self._context(job) + "\n\n" + q}]})
            r.raise_for_status()
            text = "".join(b.get("text", "") for b in r.json().get("content", [])).strip()
        except Exception as e:
            print(f"   (AI draft failed: {e})")
            return ""
        return "" if text.upper().startswith("SKIP") else text

    def cover_letter(self, job: dict) -> str:
        return self.ask(job, "Write a short, specific cover letter (under 250 words) for this role. "
                             "No placeholders, no generic filler.", max_tokens=700)


def resume_text(path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        return "\n".join((pg.extract_text() or "") for pg in PdfReader(str(path)).pages)
    except Exception:
        return ""
