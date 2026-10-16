# Job Autopilot 🤖

Finds new **software engineering, ML/data, and product management** roles from the job lists students actually trust, opens each application in a real browser, **fills in every field it can from your profile, attaches the right resume — and then stops.** You review the form and click **Submit** yourself.

```
jobagent fetch     # pull ~10k listings from 9+ sources → keep the ones that match you
jobagent list      # ranked queue: freshest + dream companies first
jobagent apply     # opens the next 5, pre-filled. You review → Submit → next one
```

## Why "you click Submit"

Auto-submitting bots spray bad applications (wrong resume, a hallucinated answer, an "I certify" box ticked for you) and some ATSes flag them. Here the agent does the tedious 90% and you keep the 10% that matters: a final read, and the click. The code enforces this — it refuses to click any submit control, and never ticks consent/attestation boxes.

## Where jobs come from

| Source | What | How it's read |
|---|---|---|
| [SimplifyJobs/Summer2027-Internships](https://github.com/SimplifyJobs/Summer2027-Internships) | Internships (SWE, PM, AI/ML, data…) | Structured `listings.json` |
| [SimplifyJobs/New-Grad-Positions](https://github.com/SimplifyJobs/New-Grad-Positions) | New grad roles | Structured `listings.json` |
| [speedyapply/2027-SWE-College-Jobs](https://github.com/speedyapply/2027-SWE-College-Jobs) | SWE intern + new grad, with pay | README table |
| [speedyapply/2027-AI-College-Jobs](https://github.com/speedyapply/2027-AI-College-Jobs) | AI/ML intern + new grad | README table |
| [jobright-ai](https://github.com/jobright-ai) SWE / PM / Data repos | Daily new grad & intern lists | README table |
| Greenhouse / Lever / Ashby boards | Your dream companies, polled directly | Public JSON APIs |

All are in `config/settings.yaml` — add, remove, or bump the year when a new season's repo appears. Listings are de-duplicated across sources (tracking params stripped, same company + title merged).

## Setup (≈10 minutes)

```bash
git clone https://github.com/<you>/job-autopilot && cd job-autopilot
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[ai]"
python -m playwright install chromium                 # only needed if you don't have Google Chrome

jobagent init                    # creates config/profile.yaml + config/settings.yaml
```

1. **Fill in `config/profile.yaml`** — name, contact links, school, work authorization, EEO preferences. It's git-ignored, so it never gets pushed.
2. **Drop your resume PDF(s) into `resumes/`** — e.g. `resume_swe.pdf` and `resume_pm.pdf`. The agent picks the one matching each job's category.
3. **Tune `config/settings.yaml`** — roles, levels, locations, sponsorship needs, dream companies, max posting age.

## Applying

```bash
jobagent fetch
jobagent apply -n 10 --role pm          # or --role swe / ml_data, --level intern / newgrad
jobagent apply 3f9a1c2                  # one specific job id from `jobagent list`
```

For each job a browser window opens and the form is filled:

- 🟢 **green** — filled from your profile (or an answer you gave before)
- 🟡 **yellow** — drafted by AI (only if you turn it on) — read these!
- 🟠 **orange** — needs you (unknown question, "I certify…" boxes, missing resume)
- 🔴 **red dashed** — the Submit button. Yours to click.

In the terminal: **Enter** = I submitted it · `s` skip · `c` posting closed · `f` re-fill · `n` add a note · `q` quit. When the "thanks for applying" page loads it's detected and logged automatically. Multi-page forms (Workday, iCIMS) are re-scanned as you click **Next**, and "Apply" buttons that open a new tab are followed.

**It learns:** anything you type into a field it couldn't answer is saved to `data/answers.json` and reused on the next application with the same question (company-specific answers like "Why Stripe?" are not reused).

**Logins stay signed in:** the browser profile lives in `data/browser-profile`, so log into Workday/LinkedIn once and it remembers. The agent never types passwords or creates accounts for you.

## Tracking

```bash
jobagent stats                                  # applied / skipped / interviewing / offers
jobagent mark 3f9a1c2 interviewing --note "recruiter call Fri"
jobagent export --out applications.csv          # open in Sheets/Excel
```

A screenshot of every filled form is saved to `data/screenshots/` before you submit — handy when a recruiter asks what you answered.

## Optional: AI-drafted answers

Set `llm.enabled: true` in `config/settings.yaml` and export `ANTHROPIC_API_KEY`. For required questions the rules don't recognize ("Why are you interested in this role?"), Claude drafts an answer **using only your profile and resume text**, and it's highlighted yellow for you to edit. `draft_cover_letters: true` also writes a short tailored cover letter per job into `data/cover_letters/`.

## Daily digest on GitHub (no laptop needed)

`.github/workflows/daily-jobs.yml` runs every morning on GitHub Actions and opens an issue listing new matching roles, so you get a GitHub notification/email. It uses `config/settings.yaml` (commit yours) or falls back to the example. Disable it in the Actions tab if you don't want it.

## Supported application forms

Works on any standard HTML form, with extra handling for the common ATSes: **Greenhouse** (incl. embedded iframes and react-select dropdowns), **Lever** (jumps straight to `/apply`), **Ashby** (`/application`), **Workday / iCIMS-style** multi-step forms, plus Yes/No radios, state & country pickers, EEO questions, and file uploads. Jobright links open Jobright's page first — click its Apply button and the agent picks up the employer's form in the new tab.

## Be a good citizen

- Only apply to roles you'd genuinely take; quality beats volume.
- Read every AI draft before submitting — you're accountable for what's sent.
- Respect site terms. This tool is designed for career sites/ATS forms you're applying through anyway; don't point it at LinkedIn Easy Apply in bulk (that violates LinkedIn's ToS and gets accounts restricted).

## Development

```bash
pip install -e ".[dev]" && pytest -q
```

Tests fill realistic Greenhouse-style and Workday-style forms headlessly and assert the Submit button is never pressed.
