"""Decide what kind of role a posting is, and whether it's early-career."""
from __future__ import annotations

import re

_PM = re.compile(
    r"\b(product manag\w*|associate product|apm\b|product owner|technical product|"
    r"product analyst|product operations|program manag\w*|tpm\b)", re.I)
_ML = re.compile(
    r"\b(machine learning|ml\b|ai\b|a\.i\.|artificial intelligence|deep learning|nlp|computer vision|"
    r"llm|data scien\w*|data engineer\w*|data analy\w*|analytics engineer|research (scientist|engineer)|"
    r"applied scientist|mlops|perception)", re.I)
_SWE = re.compile(
    r"\b(software|swe\b|sde\b|developer|programmer|full[\s-]?stack|front[\s-]?end|back[\s-]?end|"
    r"mobile|ios|android|web|devops|site reliability|sre\b|platform|infrastructure|cloud|"
    r"security engineer|cyber ?security|systems? engineer|qa engineer|test engineer|sdet|"
    r"forward deployed|solutions engineer|computer science|engineer(ing)? intern|new grad engineer)", re.I)
_QUANT = re.compile(r"\b(quant\w*|trading|trader)\b", re.I)
_HW = re.compile(r"\b(hardware|electrical|embedded|fpga|asic|firmware|rf\b|mechanical|silicon|chip|"
                 r"analog|circuit|verification engineer)", re.I)

_INTERN = re.compile(r"\b(intern(ship)?s?|co-?op|apprentice\w*|summer (20\d\d|analyst|associate)|"
                     r"(fall|winter|spring) 20\d\d)\b", re.I)
_NEWGRAD = re.compile(r"\b(new grad\w*|new college grad\w*|ncg|graduate|grad\b|entry[\s-]?level|early[\s-]?career|"
                      r"university|campus|junior|jr\.?|associate|engineer i\b|developer i\b|level 1|"
                      r"l1\b|20(26|27) start|rotational|residen(cy|t))", re.I)
_SENIOR = re.compile(r"\b(senior|sr\.?|staff|principal|lead|director|head of|vp\b|vice president|"
                     r"manager,? (engineering|software)|engineering manager|architect|"
                     r"(ii|iii|iv)\b|level [3-9])", re.I)

# Simplify's JSON category names -> ours
SIMPLIFY_CATEGORIES = {
    "software": "swe", "software engineering": "swe",
    "ai/ml/data": "ml_data", "data science, ai & machine learning": "ml_data",
    "product": "pm", "product management": "pm",
    "quant": "quant", "quantitative finance": "quant",
    "hardware": "hardware", "hardware engineering": "hardware",
}


def classify_category(title: str, hint: str = "") -> str:
    """Order matters: 'AI Product Manager' is PM, 'ML Software Engineer' is ml_data."""
    if hint:
        mapped = SIMPLIFY_CATEGORIES.get(hint.strip().lower())
        if mapped:
            return mapped
    if _PM.search(title):
        return "pm"
    if _ML.search(title):
        return "ml_data"
    if _QUANT.search(title):
        return "quant"
    if _SWE.search(title):
        return "swe"
    if _HW.search(title):
        return "hardware"
    return "other"


def classify_level(title: str, hint: str = "") -> str:
    # The title wins over the list it came from: new-grad lists often include co-ops.
    if _INTERN.search(title):
        return "intern"
    if hint in ("intern", "newgrad"):
        return hint
    if _SENIOR.search(title):
        return "senior"
    if _NEWGRAD.search(title):
        return "newgrad"
    return "unknown"


def is_senior(title: str) -> bool:
    # "Senior" in "Summer 2027 Intern - Senior Design" etc. is rare; interns win.
    return bool(_SENIOR.search(title)) and not _INTERN.search(title)
