import time

from jobagent.apply.fieldmap import pick_option, resolve
from jobagent.classify import classify_category, classify_level
from jobagent.models import Job, normalize_url
from jobagent.ranking import keep
from jobagent.sources.markdown_table import parse_tables

SPEEDY = """
## 2027 USA SWE Internships :books::eagle:
### FAANG+
| Company | Position | Location | Salary | Posting | Age |
|---|---|---|---|---|---|
| <a href="https://www.figma.com"><strong>Figma</strong></a> | Software Engineer Intern - 2027 | San Francisco, CA | $60/hr | <a href="https://boards.greenhouse.io/figma/jobs/1?gh_jid=1"><img src="x" alt="Apply"/></a> | 2d |
### Other
| Company | Position | Location | Salary | Posting | Age |
|---|---|---|---|---|---|
| <a href="https://acme.com"><strong>Acme</strong></a> | Product Manager Intern | Remote | | <a href="https://jobs.lever.co/acme/abc">Apply</a> | 40d |
## 2027 USA SWE New Grad
| Company | Position | Location | Salary | Posting | Age |
|---|---|---|---|---|---|
| <a href="https://x.com"><strong>Xco</strong></a> | Software Engineer I | NYC | | <a href="https://x.com/apply">Apply</a> | 1d |
"""

JOBRIGHT = """
| Company | Job Title | Location | Work Model | Date Posted |
| ----- | --------- |  --------- | ---- | ------- |
| **[Safeway](http://www.safeway.com)** | **[Front End Entry Level](https://jobright.ai/jobs/info/1?utm_campaign=x)** | Colville, WA, United States | On Site | Oct 15 |
| **[Acme](http://acme.com)** | **[Associate Product Manager](https://jobright.ai/jobs/info/2)** | Remote | Remote | Oct 09 |
"""

SIMPLIFY_MD = """
| Company | Role | Location | Application | Age |
|---|---|---|---|---|
| **[Stripe](https://simplify.jobs/c/Stripe)** | Software Engineer – New Grad | Seattle, WA</br>SF | <a href="https://stripe.com/jobs/1">Apply</a> | 0d |
| ↳ | Software Engineer – New Grad | Toronto, ON, Canada | <a href="https://stripe.com/jobs/2">Apply</a> | 0d |
| Closed Co | SWE Intern | NYC | 🔒 | 3d |
"""


def test_speedyapply_sections_and_tags():
    jobs = parse_tables(SPEEDY, "speedy")
    assert [j.company for j in jobs] == ["Figma", "Acme", "Xco"]
    assert jobs[0].level == "intern" and jobs[0].category == "swe" and "faang" in jobs[0].tags
    assert jobs[0].url.startswith("https://boards.greenhouse.io/figma/jobs/1")
    assert jobs[1].category == "pm" and "faang" not in jobs[1].tags
    assert jobs[2].level == "newgrad"
    assert 1.5 * 86400 < time.time() - jobs[0].date_posted < 2.5 * 86400


def test_jobright_markdown_links():
    jobs = parse_tables(JOBRIGHT, "jobright", default_level="newgrad")
    assert jobs[0].company == "Safeway" and jobs[0].title == "Front End Entry Level"
    assert jobs[0].url.startswith("https://jobright.ai/jobs/info/1")
    assert jobs[1].category == "pm"


def test_simplify_markdown_arrow_rows_and_closed():
    jobs = parse_tables(SIMPLIFY_MD, "simplify-md", default_level="newgrad")
    assert [j.company for j in jobs] == ["Stripe", "Stripe"]
    assert jobs[0].locations == ["Seattle, WA", "SF"]


def test_classification():
    assert classify_category("AI Product Manager Intern") == "pm"
    assert classify_category("Machine Learning Engineer, New Grad") == "ml_data"
    assert classify_category("Backend Software Engineer") == "swe"
    assert classify_category("Accountant") == "other"
    assert classify_level("Co-op - Software Engineer", "newgrad") == "intern"
    assert classify_level("Senior Software Engineer") == "senior"
    assert classify_level("Software Engineer I") == "newgrad"


def test_filters():
    s = {"roles": ["swe", "pm"], "levels": ["intern", "newgrad"], "max_age_days": 21,
         "countries_exclude": ["Canada"], "locations": ["CA"], "include_remote": True, "needs_sponsorship": True}
    now = time.time()
    mk = lambda **k: Job(**{"source": "t", "company": "A", "title": "Software Engineer Intern", "url": "u",
                            "category": "swe", "level": "intern", "date_posted": int(now), "locations": ["San Jose, CA"], **k})
    assert keep(mk(), s)[0]
    assert not keep(mk(locations=["Toronto, ON, Canada"]), s)[0]
    assert keep(mk(locations=["Remote"]), s)[0]
    assert not keep(mk(locations=["Austin, TX"]), s)[0]
    assert not keep(mk(date_posted=int(now - 40 * 86400)), s)[0]
    assert not keep(mk(sponsorship="Does Not Offer Sponsorship"), s)[0]
    assert not keep(mk(title="Senior Software Engineer"), s)[0]


def test_url_dedupe():
    assert normalize_url("https://Jobs.Lever.co/acme/1/?utm_source=simplify&ref=x") == "https://jobs.lever.co/acme/1"


def test_question_mapping():
    p = {"work": {"authorized_to_work_us": "Yes", "needs_sponsorship_now_or_future": "No"}}
    assert resolve("Are you legally authorized to work in the US without employer sponsorship?", p, {})[0] == "Yes"
    assert resolve("Will you now or in the future require visa sponsorship?", p, {})[0] == "No"
    p2 = {"work": {"authorized_to_work_us": "Yes", "needs_sponsorship_now_or_future": "Yes"}}
    assert resolve("Are you authorized to work in the US without sponsorship?", p2, {})[0] == "No"


def test_pick_option():
    assert pick_option(["Select...", "Yes", "No"], "No") == 2
    assert pick_option(["", "Alabama", "California"], "CA") == 2
    assert pick_option(["Male", "Female", "I don't wish to answer"], "Decline to self-identify") == 2
    assert pick_option(["Bachelor's Degree", "Master's Degree"], "Master's") == 1
    assert pick_option(["Canada", "United States of America"], "United States") == 1
    assert pick_option(["Red", "Blue"], "Green") == -1
