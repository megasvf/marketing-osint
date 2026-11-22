"""Collector — LinkedIn public company page (guest view, no login): people who list the company as their
employer, size band, HQ, founded year, followers. Optional parent-company page.

Members on LinkedIn are a proxy for team size (not everyone lists an employer; contractors may).
Pages are found from linkedin.com/company links in data/<domain>/*.json, then slug guesses; a page is accepted only
when its Website field points to the domain (or a --sibling domain). `--parent <slug>` is fetched without that check
and labelled as the parent (for example a holding that owns the company).

Usage: python collectors/linkedin.py example.com --brand Example [--slug example-inc] [--sibling example.org --slug example-org] [--parent holding-slug]
"""
import argparse
import html
import json
import re
import time

from common import ROOT, SESSION, write_source

BASE = "https://www.linkedin.com/company/"


def field(page, label):
    m = re.search(label + r"\s*</dt>\s*<dd[^>]*>\s*(.*?)\s*</dd>", page, re.S | re.I)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", m.group(1)))).strip() if m else None


def parse(page):
    title = re.search(r"<title>(.*?)\s*\|\s*LinkedIn</title>", page)
    emp = re.search(r'"numberOfEmployees"[^}]*?"value":\s*(\d+)', page)
    fol = re.search(r'([\d,]+) followers on LinkedIn', page)
    site = field(page, "Website") or ""
    return {"name": html.unescape(title.group(1)) if title else None,
            "members_on_linkedin": int(emp.group(1)) if emp else None,
            "size_band": field(page, "Company size"), "hq": field(page, "Headquarters"),
            "founded": field(page, "Founded"), "industry": field(page, "Industry"),
            "followers": int(fol.group(1).replace(",", "")) if fol else None,
            "website": site.split()[0] if site else None}


def get(slug, retry=True):
    time.sleep(3)  # LinkedIn answers 999 to bursts
    try:
        r = SESSION.get(BASE + slug + "/", timeout=25, allow_redirects=True)
    except Exception as e:
        return None, f"{slug}: {e.__class__.__name__}"
    if r.status_code == 999 and retry:
        time.sleep(20)
        return get(slug, retry=False)
    if r.status_code != 200 or "numberOfEmployees" not in r.text and "Company size" not in r.text:
        return None, f"{slug}: HTTP {r.status_code}" + (" (login wall)" if r.status_code in (999, 302) else "")
    return parse(r.text), None


def candidates(domain, brand):
    seen = []
    for f in (ROOT / "data" / domain).glob("*.json"):
        if f.name.startswith("_") or f.name in ("analysis.json", "linkedin.json"):
            continue
        for s in re.findall(r"linkedin\.com/company/([A-Za-z0-9_-]+)", f.read_text(encoding="utf-8", errors="ignore")):
            if s not in seen:
                seen.append(s)
    label = re.sub(r"[^a-z0-9]", "", domain.split(".")[0].lower())
    b = re.sub(r"[^a-z0-9]+", "-", brand.lower()).strip("-")
    for s in (b, label, f"{label}-{domain.split('.')[-1]}", f"{b}-inc", f"{b}hq"):
        if s and s not in seen:
            seen.append(s)
    return seen


def text_of(d, who):
    parts = [f"LinkedIn ({who}): {d['members_on_linkedin']} members list {d['name']} as their employer" if d.get("members_on_linkedin") else f"LinkedIn ({who}): {d['name']}"]
    for k, lab in (("size_band", "size band"), ("hq", "HQ"), ("founded", "founded"), ("followers", "followers")):
        if d.get(k):
            parts.append(f"{lab} {d[k]:,}" if isinstance(d[k], int) else f"{lab} {d[k]}")
    return "; ".join(parts) + "."


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("domain")
    ap.add_argument("--brand")
    ap.add_argument("--alt", action="append", default=[])
    ap.add_argument("--sibling", action="append", default=[])
    ap.add_argument("--parent", action="append", default=[])
    ap.add_argument("--slug", action="append", default=[], help="company or sibling page slug to try first")
    a = ap.parse_args()
    brand = a.brand or a.domain.split(".")[0].capitalize()
    hosts = [a.domain] + a.sibling
    items, notes = [], []
    found_company = False
    for slug in a.slug + [c for c in candidates(a.domain, brand) if c not in a.slug]:
        if found_company and slug not in a.slug:
            break  # one company page is enough; explicit slugs (siblings) are always tried
        d, err = get(slug)
        if err:
            notes.append(err)
            continue
        site = (d.get("website") or "").lower()
        if not any(h.lower() in site for h in hosts):
            notes.append(f"{slug}: rejected, website {site[:40] or 'none'}")
            continue
        found_company = True
        items.append({"type": "metric", "text": text_of(d, "company page"), "quote": d.get("size_band") or "",
                      "url": BASE + slug + "/", "date": None, "meta": {"role": "company", "slug": slug, **d}})
    for slug in a.parent:
        d, err = get(slug)
        if err:
            notes.append(f"parent {err}")
            continue
        items.append({"type": "metric", "text": text_of(d, "parent company"), "quote": d.get("size_band") or "",
                      "url": BASE + slug + "/", "date": None, "meta": {"role": "parent", "slug": slug, **d}})
    status = "ok" if any(i["meta"]["role"] == "company" for i in items) else ("partial" if items else "unavailable")
    note = ("Members = people who list the company as employer on its public LinkedIn page (guest view, no login); "
            "a proxy for headcount, not an exact count. " + "; ".join(notes))
    write_source(a.domain, "linkedin", status, items, note.strip())
    print(json.dumps([i["text"] for i in items], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
