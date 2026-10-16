"""Open each job in a real browser window, fill it, and wait for YOU to submit."""
from __future__ import annotations

import json
import queue
import re
import threading
import time
from pathlib import Path

from .. import config
from ..llm import Drafter, resume_text
from .filler import FillContext, fill_page, looks_submitted, read_values, show_banner

HELP = ("   [Enter]=I submitted it  s=skip  c=posting closed  f=re-fill  n=add note  q=quit\n"
        "   (submissions are detected automatically when the confirmation page loads)")


def _apply_url(url: str) -> str:
    """Jump straight to the form on ATSes that split the posting from the application."""
    if re.match(r"https://jobs\.lever\.co/[^/]+/[0-9a-f-]{36}/?$", url):
        return url.rstrip("/") + "/apply"
    if re.match(r"https://jobs\.ashbyhq\.com/[^/]+/[0-9a-f-]{36}/?$", url):
        return url.rstrip("/") + "/application"
    return url


def pick_resume(profile: dict, category: str) -> Path | None:
    resumes = profile.get("resumes") or {}
    for key in (category, "default"):
        if resumes.get(key):
            p = config.resolve(resumes[key])
            if p.exists():
                return p
    return None


class AnswerBank:
    def __init__(self, path: Path):
        self.path = path
        self.data = json.loads(path.read_text()) if path.exists() else {}

    def learn(self, new: dict, company: str) -> int:
        n = 0
        for q, a in new.items():
            # company-specific or long-form answers ("Why Stripe?") must not leak into other applications
            if len(a) > 200 or (company and company.lower() in a.lower()):
                continue
            if self.data.get(q) != a:
                self.data[q] = a
                n += 1
        if n:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, indent=2, sort_keys=True))
        return n


def _stdin_reader(q: "queue.Queue[str]") -> None:
    while True:
        try:
            q.put(input())
        except EOFError:
            q.put("q")
            return


def run(jobs: list[dict], db, settings: dict, profile: dict) -> None:
    from playwright.sync_api import sync_playwright

    apply_cfg = settings.get("apply", {})
    llm_cfg = settings.get("llm", {})
    bank = AnswerBank(config.DATA / "answers.json")
    (config.DATA / "screenshots").mkdir(parents=True, exist_ok=True)

    cmds: "queue.Queue[str]" = queue.Queue()
    threading.Thread(target=_stdin_reader, args=(cmds,), daemon=True).start()

    with sync_playwright() as pw:
        launch = dict(user_data_dir=str(config.DATA / "browser-profile"), headless=False,
                      viewport=None, args=["--start-maximized"])
        channel = apply_cfg.get("browser_channel", "chrome")
        try:
            browser = pw.chromium.launch_persistent_context(channel=channel or None, **launch)
        except Exception:
            print("   (Chrome not found - using bundled Chromium)")
            browser = pw.chromium.launch_persistent_context(**launch)

        for n, job in enumerate(jobs, 1):
            job = dict(job)
            resume = pick_resume(profile, job.get("category", ""))
            drafter = None
            if llm_cfg.get("enabled"):
                drafter = Drafter(llm_cfg.get("model", "claude-sonnet-5-5"), profile,
                                  resume_text(resume) if resume else "")
                if not drafter.available:
                    print("   (llm.enabled but ANTHROPIC_API_KEY isn't set - skipping AI drafts)")
                    drafter = None
            cl_text, cl_file = "", None
            if drafter and llm_cfg.get("draft_cover_letters"):
                cl_text = drafter.cover_letter(job)
                if cl_text:
                    safe = re.sub(r"[^A-Za-z0-9]+", "_", job["company"])[:40]
                    cl_file = config.DATA / "cover_letters" / f"{safe}_{job['id']}.txt"
                    cl_file.parent.mkdir(parents=True, exist_ok=True)
                    cl_file.write_text(cl_text)

            ctx = FillContext(profile=profile, job=job, answers=bank.data, resume=resume,
                              cover_letter_text=cl_text, cover_letter_file=cl_file, drafter=drafter,
                              leave_consent=apply_cfg.get("leave_consent_boxes_for_me", True))

            print(f"\n[{n}/{len(jobs)}] {job['company']} — {job['title']}")
            print(f"   {job['url']}")
            print(f"   resume: {resume.name if resume else 'NONE FOUND - attach one yourself'}")

            page = browser.new_page()
            pages = [page]

            def on_page(p, pages=pages):                   # "Apply" often opens a new tab
                pages.append(p)
            browser.on("page", on_page)
            try:
                page.goto(_apply_url(job["url"]), wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(2500)
            except Exception as e:
                print(f"   ! page failed to load: {str(e).splitlines()[0]}")

            fill_page(page, ctx)
            c = ctx.counts()
            print(f"   filled {c['filled']} · AI drafts {c['ai']} · needs you {c['you']}")
            if apply_cfg.get("screenshot_before_submit", True):
                try:
                    page.screenshot(path=str(config.DATA / "screenshots" / f"{job['id']}.png"), full_page=True)
                except Exception:
                    pass
            print(HELP)

            outcome, note, last_scan = None, None, time.time()
            typed: dict = {}                                  # what you typed into fields we couldn't answer
            while outcome is None:
                live = [p for p in pages if not p.is_closed()]
                if not live:
                    outcome = "skipped"
                    print("   window closed - marked skipped")
                    break
                active = live[-1]
                try:
                    active.wait_for_timeout(400)          # also lets Playwright process browser events
                except Exception:
                    continue
                if time.time() - last_scan > 2.5:         # new step of a multi-page form / new tab
                    last_scan = time.time()
                    try:
                        typed.update(read_values(active, ctx.unknown_labels))   # keep it before the page changes
                        before = len(ctx.statuses)
                        fill_page(active, ctx, only_new=True)
                        if len(ctx.statuses) > before:
                            c = ctx.counts()
                            print(f"   new fields found & filled · total filled {c['filled']} · needs you {c['you']}")
                        if looks_submitted(active):
                            bank.learn(typed, job["company"])
                            outcome = "applied"
                            print("   ✓ confirmation page detected - marked applied")
                            break
                    except Exception:
                        pass
                try:
                    cmd = cmds.get_nowait().strip().lower()
                except queue.Empty:
                    continue
                if cmd in ("", "a", "applied", "y"):
                    try:
                        typed.update(read_values(active, ctx.unknown_labels))
                    except Exception:
                        pass
                    bank.learn(typed, job["company"])
                    outcome = "applied"
                elif cmd == "s":
                    outcome = "skipped"
                elif cmd == "c":
                    outcome = "closed"
                elif cmd == "f":
                    fill_page(active, ctx)
                    show_banner(active, ctx)
                    print("   re-filled")
                elif cmd.startswith("n"):
                    note = cmd[1:].strip() or None
                    print("   type your note and press Enter:")
                    note = note or cmds.get().strip()
                    print("   note saved")
                elif cmd == "q":
                    print("   bye - this job stays in your queue")
                    browser.close()
                    return
                else:
                    print(HELP)

            db.set_status(job["id"], outcome, resume=str(resume.name) if resume else None, note=note)
            print(f"   → {outcome}")
            browser.remove_listener("page", on_page)
            for p in pages:
                if not p.is_closed():
                    p.close()
        browser.close()
    print("\nQueue done. `jobagent stats` shows your totals.")
