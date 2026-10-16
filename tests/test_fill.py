"""End-to-end: fill realistic forms headlessly and prove Submit is never pressed."""
from pathlib import Path

import pytest

from jobagent.apply.filler import FillContext, fill_page, read_values

pw = pytest.importorskip("playwright.sync_api")
FIX = Path(__file__).parent / "fixtures"

PROFILE = {
    "personal": {"first_name": "Jane", "last_name": "Doe", "email": "jane@example.com", "phone": "415-555-0100",
                 "linkedin": "https://linkedin.com/in/jane", "github": "https://github.com/jane", "city": "San Francisco",
                 "state": "CA", "country": "United States"},
    "education": {"school": "University of San Francisco", "degree": "Master's", "graduation_date": "05/2027"},
    "work": {"authorized_to_work_us": "Yes", "needs_sponsorship_now_or_future": "No", "willing_to_relocate": "Yes",
             "how_did_you_hear": "Online job board", "earliest_start_date": "06/2027"},
    "eeo": {"gender": "Decline to self-identify", "veteran": "I am not a protected veteran",
            "disability": "I do not want to answer"},
}


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture()
def resume(tmp_path):
    f = tmp_path / "resume.pdf"
    f.write_bytes(b"%PDF-1.4 test")
    return f


def ctx_for(resume, answers=None):
    return FillContext(profile=PROFILE, job={"company": "Acme", "title": "SWE"}, answers=answers or {}, resume=resume)


def val(page, sel):
    return page.eval_on_selector(sel, "e => e.tagName === 'SELECT' ? e.options[e.selectedIndex].text : e.value")


def test_greenhouse_like_form(browser, resume):
    page = browser.new_page()
    page.goto((FIX / "greenhouse_like.html").as_uri())
    ctx = ctx_for(resume)
    fill_page(page, ctx)

    assert val(page, "#first_name") == "Jane"
    assert val(page, "#last_name") == "Doe"
    assert val(page, "#email") == "jane@example.com"
    assert val(page, "#li") == "https://linkedin.com/in/jane"
    assert val(page, "#gh") == "https://github.com/jane"
    assert val(page, "#school") == "University of San Francisco"
    assert val(page, "#degree") == "Master's Degree"
    assert val(page, "#grad") == "05/2027"                      # graduation date, not the school name
    assert val(page, "#auth") == "Yes"
    assert val(page, "#spons") == "No"
    assert val(page, "#state") == "California"                  # CA -> California
    assert val(page, "#gender") == "Decline To Self Identify"
    assert val(page, "#vet") == "I am not a protected veteran"
    assert val(page, "#dis") == "I do not want to answer"
    assert page.eval_on_selector("#resume", "e => e.files[0].name") == "resume.pdf"
    assert page.eval_on_selector("input[name=reloc][value='1']", "e => e.checked")
    # left for the human:
    assert not page.eval_on_selector("#agree", "e => e.checked"), "consent boxes must stay unticked"
    assert val(page, "#why") == ""
    assert page.evaluate("() => !!document.getElementById('__ja_bar')")
    assert not page.evaluate("() => !!window.__submitted"), "agent must never submit"
    assert "dashed" in page.eval_on_selector("#submit_app", "e => e.style.outline")


def test_learns_answers_you_type(browser, resume):
    page = browser.new_page()
    page.goto((FIX / "greenhouse_like.html").as_uri())
    ctx = ctx_for(resume)
    fill_page(page, ctx)
    page.fill("#fav", "Functional")
    page.fill("#why", "Because Acme builds great tools")   # company-specific: session.AnswerBank drops these
    learned = read_values(page, ctx.unknown_labels)
    assert learned.get("favorite programming paradigm") == "Functional"

    page2 = browser.new_page()
    page2.goto((FIX / "greenhouse_like.html").as_uri())
    fill_page(page2, ctx_for(resume, answers=learned))
    assert val(page2, "#fav") == "Functional"


def test_multistep_spa_with_combobox(browser, resume):
    page = browser.new_page()
    page.goto((FIX / "multistep_spa.html").as_uri())
    ctx = ctx_for(resume)
    fill_page(page, ctx)
    inputs = page.locator("#app input")
    assert inputs.nth(0).input_value() == "Jane"
    assert inputs.nth(1).input_value() == "Doe"
    assert inputs.nth(2).input_value() == "jane@example.com"
    assert page.inner_text(".select__single-value") == "United States of America"

    page.click("#next")                       # the human moves to the next step
    fill_page(page, ctx, only_new=True)       # session loop does this automatically
    assert page.eval_on_selector("input[name=q18][value=y]", "e => e.checked")
    assert page.input_value("#start") == "2027-06-01"
    assert not page.evaluate("() => !!window.__submitted")
