"""Fill every question on an application page from your profile. Never submits."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .fieldmap import is_consent, norm, pick_option, resolve, to_date_input

JS = (Path(__file__).with_name("page.js")).read_text(encoding="utf-8")

_RESUME = re.compile(r"resume|résumé|\bcv\b|curriculum", re.I)
_COVER = re.compile(r"cover ?letter|motivation letter", re.I)


@dataclass
class FillContext:
    profile: dict
    job: dict
    answers: dict                                # learned question -> answer
    resume: Path | None = None
    cover_letter_text: str = ""
    cover_letter_file: Path | None = None
    drafter: object | None = None                # llm.Drafter or None
    leave_consent: bool = True
    statuses: dict = field(default_factory=dict) # ref -> filled|learned|ai|you|consent
    unknown_labels: dict = field(default_factory=dict)  # ref -> label (for learning)

    def counts(self) -> dict:
        c = {"filled": 0, "ai": 0, "you": 0}
        for s in self.statuses.values():
            c["filled" if s in ("filled", "learned") else "you" if s in ("you", "consent") else s] += 1
        return c


def _ensure_js(frame) -> bool:
    try:
        frame.evaluate(JS)
        return True
    except Exception:
        return False  # detached / cross-origin weirdness - skip this frame


def _loc(frame, ref: str):
    return frame.locator(f'[data-ja="{ref}"]').first


def _assert_not_submit(frame, ref: str) -> None:
    """Belt and braces: refuse to ever click something that submits a form."""
    is_submit = frame.evaluate(
        """r => { const el = document.querySelector(`[data-ja="${r}"]`);
                  return !!el && (el.type === 'submit' || (el.tagName === 'BUTTON' && el.type !== 'button')); }""", ref)
    if is_submit:
        raise RuntimeError("refusing to click a submit control")


def _value_for(f: dict, ctx: FillContext) -> tuple[str, str]:
    label = f.get("label", "")
    value, how = resolve(label, ctx.profile, ctx.answers)
    if value or not ctx.drafter or not getattr(ctx.drafter, "available", False):
        return value, ("learned" if how == "learned" else "filled") if value else ""
    # Only spend an AI call on questions that matter: required ones, or long-form text.
    if not (f.get("required") or f["kind"] == "textarea"):
        return "", ""
    opts = [o if isinstance(o, str) else o.get("text", "") for o in f.get("options", [])] or None
    drafted = ctx.drafter.ask(ctx.job, label, opts)
    return (drafted, "ai") if drafted else ("", "")


def _fill_field(frame, f: dict, ctx: FillContext) -> str:
    kind, label, ref = f["kind"], f.get("label", ""), f["ref"]

    if kind == "file":
        if f.get("value"):
            return "filled"
        if _COVER.search(label):
            if ctx.cover_letter_file and ctx.cover_letter_file.exists():
                _loc(frame, ref).set_input_files(str(ctx.cover_letter_file))
                return "ai"
            return "you" if f.get("required") else ""
        if _RESUME.search(label) or "pdf" in f.get("accept", "") or not label:
            if ctx.resume and ctx.resume.exists():
                _loc(frame, ref).set_input_files(str(ctx.resume))
                return "filled"
        return "you"

    if kind == "textarea" and _COVER.search(label) and ctx.cover_letter_text and not f.get("value"):
        _loc(frame, ref).fill(ctx.cover_letter_text)
        return "ai"

    if kind == "checkbox":
        if f.get("answered"):
            return "filled"
        if is_consent(label):
            return "consent" if ctx.leave_consent or f.get("required") else ""
        value, how = _value_for(f, ctx)
        if value.lower().startswith("y"):
            _assert_not_submit(frame, ref)
            _loc(frame, ref).check(force=True)
            return how
        return "you" if f.get("required") else ""

    # Already has an answer (pre-filled by the site, or by you) - leave it alone.
    if f.get("value") or f.get("answered"):
        return "filled"

    value, how = _value_for(f, ctx)
    if not value:
        ctx.unknown_labels[ref] = label
        return "you" if f.get("required") or kind in ("textarea",) else ""

    if kind in ("text", "textarea"):
        if f.get("type") == "date":
            value = to_date_input(value)
        _loc(frame, ref).fill(value)
        return how

    if kind == "select":
        i = pick_option(f["options"], value)
        if i < 0:
            ctx.unknown_labels[ref] = label
            return "you"
        _loc(frame, ref).select_option(index=i)
        return how

    if kind in ("radio", "checkboxes"):
        texts = [o["text"] for o in f["options"]]
        if kind == "checkboxes" and is_consent(label):
            return "consent"
        i = pick_option(texts, value)
        if i < 0:
            ctx.unknown_labels[ref] = label
            return "you"
        opt_ref = f["options"][i]["ref"]
        _assert_not_submit(frame, opt_ref)
        _loc(frame, opt_ref).check(force=True)
        return how

    if kind == "combobox":
        box = _loc(frame, ref)
        box.click()
        box.fill(value)
        frame.wait_for_timeout(700)
        options = frame.locator("[role=option]")
        texts = [t.strip() for t in options.all_inner_texts()][:200]
        i = pick_option(texts, value)
        if i < 0:
            box.press("Escape")
            box.fill("")
            ctx.unknown_labels[ref] = label
            return "you"
        options.nth(i).click()
        return how
    return ""


def fill_frame(frame, ctx: FillContext, only_new: bool = False) -> int:
    if not _ensure_js(frame):
        return 0
    try:
        fields = frame.evaluate("onlyNew => window.__ja.collect(onlyNew)", only_new)
    except Exception:
        return 0
    statuses = {}
    for f in fields:
        try:
            status = _fill_field(frame, f, ctx)
        except Exception as e:  # one weird widget shouldn't stop the rest
            status = "you"
            print(f"   ! couldn't fill “{f.get('label', '')[:60]}”: {str(e).splitlines()[0][:100]}")
        statuses[f["ref"]] = status
    try:
        frame.evaluate("s => window.__ja.mark(s)", statuses)
    except Exception:
        pass
    ctx.statuses.update({k: v for k, v in statuses.items() if v})
    return len(fields)


def fill_page(page, ctx: FillContext, only_new: bool = False) -> int:
    n = 0
    for frame in page.frames:
        n += fill_frame(frame, ctx, only_new)
    show_banner(page, ctx)
    return n


def show_banner(page, ctx: FillContext) -> None:
    c = ctx.counts()
    summary = {"job": f"{ctx.job.get('company', '')} — {ctx.job.get('title', '')}"[:90], **c}
    for frame in page.frames:
        try:
            if _ensure_js(frame):
                frame.evaluate("s => window.__ja.banner(s)", summary)
        except Exception:
            pass


def looks_submitted(page) -> bool:
    for frame in page.frames:
        try:
            if _ensure_js(frame) and frame.evaluate("() => window.__ja.confirmation()"):
                return True
        except Exception:
            pass
    return False


def read_values(page, refs: dict) -> dict:
    """Current values of fields we couldn't answer - so we can learn what you typed."""
    learned = {}
    for frame in page.frames:
        try:
            vals = frame.evaluate(
                """refs => { const out = {};
                    for (const r of refs) { const el = document.querySelector(`[data-ja="${r}"]`); if (!el) continue;
                      if (el.type === 'radio' || el.type === 'checkbox') {
                        const g = el.name ? document.querySelectorAll(`input[name="${CSS.escape(el.name)}"]`) : [el];
                        const c = [...g].find(x => x.checked);
                        if (c) { const l = c.id && document.querySelector(`label[for="${CSS.escape(c.id)}"]`);
                                 out[r] = (l ? l.innerText : (c.closest('label') || {}).innerText || c.value || '').trim(); }
                      } else if (el.tagName === 'SELECT') { if (el.selectedIndex > 0) out[r] = el.options[el.selectedIndex].text.trim(); }
                      else if (el.value) out[r] = el.value; }
                    return out; }""", list(refs))
            learned.update(vals)
        except Exception:
            pass
    return {norm(refs[r]): v for r, v in learned.items() if refs.get(r) and v and len(v) < 2000}
