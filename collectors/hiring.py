"""Collector 10 — hiring signals: open roles, marketing/growth roles flagged.

Finds the careers page from the site, then tries public ATS job-board APIs
(Greenhouse, Lever, Ashby, Recruitee, Workable, Personio) with slugs from the careers page or the domain.
When no ATS board is found, falls back to LinkedIn's public guest jobs search (HTML fragments, no login),
keeping only postings whose company matches the brand or the company's LinkedIn slug.

Usage: python collectors/hiring.py example.com [--brand "Example"]
"""
import os
import re
import sys
import time
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from common import SESSION, clean, fetch, page_signals, write_source

MKT = re.compile(r"market|growth|brand|content|seo|sem|ppc|paid|demand|social|community|pr\b|communications|"
                 r"lifecycle|crm|product marketing|devrel|developer relations|partnership|affiliate", re.I)
ATS_RX = re.compile(r"(greenhouse\.io|lever\.co|ashbyhq\.com|recruitee\.com|workable\.com|personio\.(?:de|com)|"
                    r"bamboohr\.com|teamtailor\.com|breezy\.hr|smartrecruiters\.com)/?([\w-]*)", re.I)


FAMILIES = [  # first match wins; counted here so reports never rely on hand counts
    ("people and G&A", r"recruit|talent|people|\bhr\b|finance|accounting|legal|counsel|payroll|risk|compliance|workplace|office|executive assistant|chief of staff"),
    ("sales", r"\bsales\b|account executive|account manager|business development|\bbdr\b|\bsdr\b|\bae\b|revenue"),
    ("marketing", r"marketing|growth|brand|content|\bseo\b|\bsem\b|ppc|paid|demand|social|community|\bpr\b|communications|"
                  r"lifecycle|\bcrm\b|devrel|developer relations|partnership|affiliate"),
    ("solutions and customer", r"solution|sales engineer|customer|support|onboarding|implementation|forward deployed|outcome|enablement|technical account"),
    ("engineering and data", r"engineer|developer|software|infrastructure|security|devops|\bsre\b|data scien|machine learning|\bml\b|research scientist|analyst"),
    ("product and design", r"product manager|product lead|\bpm\b|design|ux|researcher"),
]
FAM_RX = [(n, re.compile(rx, re.I)) for n, rx in FAMILIES]


def family(title):
    t = title.split(" (")[0]
    return next((n for n, rx in FAM_RX if rx.search(t)), "other")


def city(text):
    m = re.search(r"\(([^()]*)\)\s*$", text)
    return (m.group(1).split(",")[0].split("•")[0].strip() if m else "") or "not stated"


def summarize(items, url):
    """Metric items with role-family and city counts over the job items (computed, never by hand)."""
    from collections import Counter
    jobs = [i for i in items if i["type"] == "job" and i.get("url") and "no open roles" not in i["text"] and "only via LinkedIn" not in i["text"]]
    for i in jobs:
        i.setdefault("meta", {})["family"] = family(i["text"])
    if not jobs:
        return []
    fam = Counter(i["meta"]["family"] for i in jobs)
    depts = Counter(i["meta"].get("department") for i in jobs if i["meta"].get("department"))
    board = []
    if depts and sum(depts.values()) >= 0.7 * len(jobs):  # the board's own labels beat title rules when present
        board = [{"type": "metric", "text": f"{len(jobs)} open roles by the job board's own department labels: "
                  + ", ".join(f"{k} {v}" for k, v in depts.most_common()),
                  "url": url, "meta": {"metric": "role_departments", "total": len(jobs), "counts": dict(depts),
                                       "labelled": sum(depts.values())}}]
    cities = Counter(city(i["text"]) for i in jobs)
    by_city_fam = {c: dict(Counter(i["meta"]["family"] for i in jobs if city(i["text"]) == c)) for c, _ in cities.most_common(6)}
    return [
        *board,
        {"type": "metric", "text": f"{len(jobs)} open roles by title rules: " + ", ".join(f"{k} {v}" for k, v in fam.most_common()),
         "url": url, "meta": {"metric": "role_families", "total": len(jobs), "counts": dict(fam),
                              "rules": "first matching title rule wins: " + "; ".join(n for n, _ in FAMILIES)}},
        {"type": "metric", "text": "Open roles by city: " + ", ".join(f"{k} {v}" for k, v in cities.most_common(8)),
         "url": url, "meta": {"metric": "role_cities", "total": len(jobs), "counts": dict(cities), "families_by_city": by_city_fam}},
    ]


def boards(slug):
    """(name, api_url, parser) candidates for a slug. Parsers return (title, location, url, department or "")
    where department is the board's own team / department label."""
    return [
        ("greenhouse", f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
         lambda j: [(x["title"], x.get("location", {}).get("name", ""), x["absolute_url"],
                     ((x.get("departments") or [{}])[0] or {}).get("name") or "") for x in j.get("jobs", [])]),
        ("lever", f"https://api.lever.co/v0/postings/{slug}?mode=json",
         lambda j: [(x["text"], x.get("categories", {}).get("location", ""), x["hostedUrl"],
                     x.get("categories", {}).get("team") or x.get("categories", {}).get("department") or "") for x in j]),
        ("ashby", f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
         lambda j: [(x["title"], x.get("location", ""), x["jobUrl"], x.get("team") or x.get("department") or "")
                    for x in j.get("jobs", [])]),
        ("recruitee", f"https://{slug}.recruitee.com/api/offers/",
         lambda j: [(x["title"], x.get("location", ""), x["careers_url"], x.get("department") or "") for x in j.get("offers", [])]),
        ("workable", f"https://apply.workable.com/api/v1/widget/accounts/{slug}",
         lambda j: [(x["title"], x.get("city", ""), x["url"], x.get("department") or "") for x in j.get("jobs", [])]),
    ]


def try_boards(slugs):
    for slug in slugs:
        for name, api, parse in boards(slug):
            try:
                r = SESSION.get(api, timeout=20)
                if r.status_code == 200:
                    jobs = parse(r.json())
                    if jobs:
                        return name, api, jobs
            except Exception:
                continue
    return None, None, []


LI_GUEST = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"


LI_VARIANTS = ["{b}", "{b} SaaS", "{b} software", "{b} SDK", "{b} platform"]  # guest search ranks by keyword, so widen the net


def linkedin_guest(brand, li_slugs, pages=2):
    """Public LinkedIn guest search. Returns (jobs, error). Job = (title, location, url, posted, company)."""
    jobs, err = [], ""
    slugs = {x.lower() for x in li_slugs}
    for kw, page in [(v.format(b=brand), pg) for v in LI_VARIANTS for pg in range(pages)]:
        try:
            r = SESSION.get(f"{LI_GUEST}?keywords={quote_plus(kw)}&location=Worldwide&start={page * 10}", timeout=25)
        except Exception as e:
            err = f"LinkedIn guest request failed ({type(e).__name__})"
            break
        if r.status_code != 200:
            err = f"LinkedIn guest HTTP {r.status_code}"
            break
        cards = BeautifulSoup(r.text, "lxml").select("div.base-search-card")
        for c in cards:
            title = c.select_one(".base-search-card__title")
            sub = c.select_one(".base-search-card__subtitle")
            link = c.select_one("a.base-card__full-link")
            if not (title and sub and link):
                continue
            co = clean(sub.get_text(" "))
            co_a = sub.find("a")
            co_slug = ""
            if co_a and co_a.get("href"):
                m = re.search(r"/company/([\w-]+)", co_a["href"])
                co_slug = m.group(1).lower() if m else ""
            if not (re.search(rf"(?<!\w){re.escape(brand)}(?!\w)", co, re.I) or (co_slug and co_slug in slugs)):
                continue
            loc = c.select_one(".job-search-card__location")
            when = c.select_one("time")
            jobs.append((clean(title.get_text(" ")), clean(loc.get_text(" ")) if loc else "",
                         link["href"].split("?")[0], (when.get("datetime") if when else "") or "", co))
        time.sleep(1.5)
    return list({j[2]: j for j in jobs}.values()), err


def main(domain, brand=None):
    brand = brand or domain.split(".")[0].capitalize()
    home, html = fetch(f"https://{domain}/")
    careers = None
    ch = ""
    if html:
        for text, u in page_signals(html, home)["links"]:
            if re.search(r"career|jobs|join|hiring|work-with-us", u + " " + text, re.I):
                careers = u
                break
    slugs, page_jobs = [], []
    if careers:
        cu, ch = fetch(careers)
        if ch:
            for m in ATS_RX.finditer(ch):
                if m.group(2):
                    slugs.append(m.group(2).lower())
            # jobs listed directly on the careers page (h2/h3 titles + links)
            sig = page_signals(ch, cu)
            page_jobs = [(t, u) for t, u in sig["links"] if re.search(r"job|position|opening|role|career/", u, re.I) and len(t) > 8]
    base = domain.split(".")[0]
    slugs += [base, base.replace("-", ""), f"{base}io"]
    slugs = list(dict.fromkeys(slugs))
    ats, api, jobs = try_boards(slugs)
    items = []
    for title, loc, url, dept in jobs:
        items.append({"type": "job", "text": f"{title} ({loc})" if loc else title, "url": url,
                      "meta": {"marketing": bool(MKT.search(title)), "ats": ats, "department": dept}})
    if not items:
        for t, u in page_jobs[:30]:
            items.append({"type": "job", "text": t, "url": u, "meta": {"marketing": bool(MKT.search(t)), "ats": "careers page"}})
    li_note = ""
    if not jobs and os.environ.get("OSINT_ENABLE_LINKEDIN") == "1":  # LinkedIn guest search: opt-in, see README
        li_slugs = set(re.findall(r"linkedin\.com/company/([\w-]+)", (html or "") + (ch or "")))
        lj, lerr = linkedin_guest(brand, li_slugs)
        for title, loc, url, posted, co in lj:
            items.append({"type": "job", "text": f"{title} ({loc})" if loc else title, "url": url,
                          "date": posted or None,
                          "meta": {"marketing": bool(MKT.search(title)), "ats": "linkedin guest", "company": co}})
        li_note = (f"; LinkedIn guest search (slugs {sorted(li_slugs) or 'none'}): {len(lj)} postings matched the company"
                   + (f"; {lerr}" if lerr else "") + "; public sample only, may undercount")
    mk = sum(i["meta"]["marketing"] for i in items)
    note = f"careers page {careers or 'not found'}; ATS {ats or 'none matched'} (slugs tried {slugs}); {len(items)} roles, {mk} marketing/growth{li_note}"
    if items:
        status = "ok" if ats else "partial"
    elif careers:
        status = "partial"
        li = re.search(r"https://www\.linkedin\.com/company/[\w-]+/jobs/?", ch or "")
        if li:
            note += "; roles are listed on LinkedIn Jobs (login-gated, not scraped)"
            items.append({"type": "job", "text": "Open roles published only via LinkedIn Jobs", "url": li.group(0),
                          "meta": {"marketing": False}})
        else:
            items.append({"type": "job", "text": "Careers page found, no open roles parsed", "url": careers,
                          "meta": {"marketing": False}})
    else:
        status = "unavailable"
    if items:
        items += summarize(items, api or careers or items[0]["url"])
    return write_source(domain, "hiring", status, items, note)


def resummarize(domain):
    """Recompute the summary metrics on an existing hiring.json without fetching again."""
    import json
    from common import ROOT
    d = json.loads((ROOT / "data" / domain / "hiring.json").read_text(encoding="utf-8"))
    items = [i for i in d["items"] if (i.get("meta") or {}).get("metric") not in ("role_families", "role_cities", "role_departments")]
    url = next((i["url"] for i in items if i["type"] == "job"), "")
    items += summarize(items, url)
    return write_source(domain, "hiring", d["status"], items, d.get("note", ""))


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--summarize-only" in args:
        resummarize(args[0])
    else:
        main(args[0], args[args.index("--brand") + 1] if "--brand" in args else None)
