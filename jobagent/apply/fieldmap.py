"""Map a form question ("Will you now or in the future require sponsorship?") to an answer
from your profile, and pick the matching option in dropdowns / radio groups."""
from __future__ import annotations

import re
from typing import Callable

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan",
    "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
    "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming",
}

DECLINE_WORDS = ("decline", "prefer not", "don't wish", "do not wish", "not wish to", "rather not",
                 "choose not", "not to answer", "not to disclose", "don't want to answer",
                 "do not want to answer", "not to self", "i don't want")

# Checkboxes whose label matches this are agreements/attestations - always left for you.
CONSENT = re.compile(r"\b(agree|consent|acknowledge|certify|attest|accept|terms|privacy|policy|"
                     r"confirm that|i understand|truthful|accurate)\b", re.I)


def norm(s: str) -> str:
    s = (s or "").lower().replace("’", "'")
    s = re.sub(r"[*:?()\[\]]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _get(profile: dict, path: str) -> str:
    cur = profile
    for part in path.split("."):
        cur = cur.get(part, {}) if isinstance(cur, dict) else {}
    return "" if cur in ({}, None) else str(cur).strip()


def _full_name(p: dict) -> str:
    return f"{_get(p, 'personal.first_name')} {_get(p, 'personal.last_name')}".strip()


def _location(p: dict) -> str:
    return ", ".join(x for x in (_get(p, "personal.city"), _get(p, "personal.state")) if x)


def _pref_name(p: dict) -> str:
    return _get(p, "personal.preferred_name") or _get(p, "personal.first_name")


Resolver = Callable[[dict], str]


def P(path: str) -> Resolver:
    return lambda p: _get(p, path)


def C(value: str) -> Resolver:
    return lambda p: value


# (pattern on the normalized question text, resolver). First match wins, so order matters.
RULES: list[tuple[re.Pattern, Resolver]] = [(re.compile(rx, re.I), fn) for rx, fn in [
    (r"\b(preferred|nick) ?name", _pref_name),
    (r"first ?name|given name|legal first", P("personal.first_name")),
    (r"last ?name|surname|family name|legal last", P("personal.last_name")),
    (r"middle ?name", C("")),
    (r"^(full |legal |your )?name\b|full name|legal name|^name$", _full_name),
    (r"pronoun", P("personal.pronouns")),
    (r"e-?mail", P("personal.email")),
    (r"phone (device )?type", C("Mobile")),
    (r"country (phone )?code", P("personal.country")),
    (r"phone|mobile|telephone|cell", P("personal.phone")),
    (r"linked ?in", P("personal.linkedin")),
    (r"git ?hub", P("personal.github")),
    (r"portfolio|personal (web)?site|website|blog|other (link|url)|^url", lambda p: _get(p, "personal.portfolio") or _get(p, "personal.github")),
    (r"twitter|x\.com", C("")),
    # education
    # (most specific first: "expected graduation date from your university" is a date, not a school)
    (r"graduation year|year of graduation|grad year|class of", P("education.graduation_year")),
    (r"graduat|grad date|completion date", P("education.graduation_date")),
    (r"\bgpa\b|grade point", P("education.gpa")),
    (r"major|discipline|field of study|area of study|concentration", P("education.major")),
    (r"\bdegree\b|level of education|highest education", P("education.degree")),
    (r"school|universit|college|institution", P("education.school")),
    # work eligibility - sponsorship BEFORE authorization (sponsorship questions often say "authorized")
    (r"(authori[sz]ed|eligible|able) to work.{0,80}without.{0,40}sponsor",
     lambda p: "No" if _get(p, "work.needs_sponsorship_now_or_future").lower().startswith("y")
     else _get(p, "work.authorized_to_work_us")),
    (r"(require|need|will you).{0,60}(sponsor|visa)|sponsorship|h-?1b",P("work.needs_sponsorship_now_or_future")),
    (r"authori[sz]ed to work|legally (authori[sz]ed|eligible|able)|eligible to work|right to work|work authori[sz]ation",
     P("work.authorized_to_work_us")),
    (r"18 years|at least 18|over 18|legal age", C("Yes")),
    (r"relocat", P("work.willing_to_relocate")),
    (r"previously (worked|been employed|applied)|former employee|ever (worked|been employed)", C("No")),
    (r"start date|available to start|earliest (start|available)|availability|when can you start", P("work.earliest_start_date")),
    (r"current (company|employer)|most recent (company|employer)|^employer", P("work.current_company")),
    (r"current (job )?title|most recent title|current role|^title$", P("work.current_title")),
    (r"years of (professional |relevant )?experience|how many years", P("work.years_experience")),
    (r"salary|compensation|pay (expectation|range)|expected pay|desired pay", P("work.desired_salary")),
    (r"how did you (hear|find|learn)|where did you (hear|find)|source of (application|referral)|^source$", P("work.how_did_you_hear")),
    # location
    (r"address line 2|apt|suite", C("")),
    (r"street|address line|^address|mailing address|home address", P("personal.address")),
    (r"\bcity\b|town", P("personal.city")),
    (r"\bstate\b|province|region", P("personal.state")),
    (r"zip|postal", P("personal.zip")),
    (r"country", P("personal.country")),
    (r"location|where are you (located|based)|current residence|based in", _location),
    # voluntary self-id
    (r"hispanic|latin[oax]", P("eeo.hispanic_latino")),
    (r"\bgender\b|\bsex\b", P("eeo.gender")),
    (r"\brace\b|ethnic", P("eeo.race")),
    (r"veteran", P("eeo.veteran")),
    (r"disabilit", P("eeo.disability")),
    (r"sexual orientation|transgender|lgbt", C("Decline to self-identify")),
]]


def resolve(label: str, profile: dict, answers: dict[str, str]) -> tuple[str, str]:
    """Return (value, how) for a question label. how is 'profile', 'custom', 'learned' or ''."""
    n = norm(label)
    if not n:
        return "", ""
    # Your own regex answers beat everything.
    for rx, val in (profile.get("custom_answers") or {}).items():
        if val and re.search(rx, n, re.I):
            return str(val), "custom"
    # Exact question you've answered before on another application.
    if n in answers and answers[n]:
        return answers[n], "learned"
    for rx, fn in RULES:
        if rx.search(n):
            return fn(profile), "profile"
    return "", ""


def is_consent(label: str) -> bool:
    return bool(CONSENT.search(label or ""))


def _canon(s: str) -> str:
    s = norm(s).replace("'", "")
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()


def pick_option(options: list[str], value: str) -> int:
    """Index of the option best matching value, or -1. Handles Yes/No, decline-to-answer,
    state abbreviations, Master's vs Masters Degree, and so on."""
    if not value or not options:
        return -1
    v = _canon(value)
    opts = [_canon(o) for o in options]
    real = [i for i, o in enumerate(opts) if o and not re.match(r"^(select|choose|please select|--)", o)]

    for i in real:
        if opts[i] == v:
            return i
    if v in ("yes", "no"):
        for i in real:
            if re.match(rf"^{v}\b", opts[i]):
                return i
        return -1
    if any(d.replace("'", "") in v for d in DECLINE_WORDS) or v.startswith("decline"):
        for i in real:
            if any(d.replace("'", "") in opts[i] for d in DECLINE_WORDS):
                return i
    if value.upper() in US_STATES:
        full = _canon(US_STATES[value.upper()])
        for i in real:
            if opts[i] == full:
                return i
    if v in ("united states", "usa", "us", "united states of america"):
        for i in real:
            if opts[i] in ("united states", "usa", "us", "united states of america", "u s", "u s a"):
                return i
    for i in real:  # one contains the other ("masters" in "masters degree")
        if len(v) >= 3 and (v in opts[i] or (len(opts[i]) >= 3 and opts[i] in v)):
            return i
    vt = set(v.split())
    best, best_i = 0.0, -1
    for i in real:
        ot = set(opts[i].split())
        if not ot:
            continue
        j = len(vt & ot) / len(vt | ot)
        if j > best:
            best, best_i = j, i
    return best_i if best >= 0.5 else -1


def to_date_input(value: str) -> str:
    """'05/2027' or '2027-05' or 'May 2027' -> '2027-05-01' for <input type=date>."""
    m = re.match(r"^(\d{1,2})/(\d{4})$", value.strip())
    if m:
        return f"{m.group(2)}-{int(m.group(1)):02d}-01"
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", value.strip())
    if m:
        return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    m = re.match(r"^(\d{4})-(\d{2})$", value.strip())
    if m:
        return f"{value.strip()}-01"
    return value
