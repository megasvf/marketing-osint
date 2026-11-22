"""Collector 12 — press and news mentions via Google News RSS (last 365 days).

One query per brand term (brand plus each --alt). The brand must appear in the headline as a whole word
(the RSS description only repeats the headline and publisher), which drops fuzzy-match false positives.
Article links are Google News redirect links; the publisher site comes from the <source url> tag.

Usage: python collectors/news.py example.com [--brand "Example"] [--alt "Old Name"]
"""
import argparse
import html
import json
import re
from collections import Counter
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

from common import ROOT, SESSION, clean, write_source

PRESS = re.compile(r"prnewswire|pr newswire|businesswire|business wire|globenewswire|globe newswire|"
                   r"einpresswire|accesswire|newswire|prweb|press release", re.I)
BLOG = re.compile(r"medium|substack|blog|wordpress|dev\.to|hashnode|linkedin|reddit|quora", re.I)


def args_brand():
    ap = argparse.ArgumentParser()
    ap.add_argument("domain")
    ap.add_argument("--brand")
    ap.add_argument("--alt", action="append", default=[])
    a = ap.parse_args()
    brand = a.brand or a.domain.split(".")[0].capitalize()
    return a.domain, brand, a.alt


STOP = set("free with your that this more from have best make into what when will than them they their about "
           "build builds built need help over under most just like also made first new top get gets better check full".split())


def site_stems(domain, brand_terms):
    """Word stems from the owned-site home messaging, used to flag headlines about a namesake company."""
    f = ROOT / "data" / domain / "site.json"
    if not f.exists():
        return set()
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return set()
    text = " ".join(f"{i.get('text', '')} {i.get('quote', '')}" for i in d.get("items", [])
                    if (i.get("meta") or {}).get("kind") in ("home", "product"))
    counts = Counter(stem_list(text, brand_terms))
    return {w for w, n in counts.items() if n >= 3}  # repeated words = the company's real vocabulary


def stem_list(text, brand_terms):
    banned = {w.lower() for t in brand_terms for w in re.findall(r"\w+", t)}
    return [w[:6] for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in STOP and w not in banned]


def stems(text, brand_terms):
    return set(stem_list(text, brand_terms))


def tag(block, name):
    m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", block, re.S)
    return html.unescape(m.group(1)).strip() if m else ""


def kind_of(publisher, host):
    s = f"{publisher} {host}"
    if PRESS.search(s):
        return "press_release"
    return "blog" if BLOG.search(s) else "news"


def feed(term):
    url = (f"https://news.google.com/rss/search?q=%22{quote_plus(term)}%22+when:365d"
           "&hl=en-US&gl=US&ceid=US:en")
    try:
        r = SESSION.get(url, timeout=25)
    except Exception as e:
        return url, None, f"{term}: {type(e).__name__}"
    if r.status_code != 200:
        return url, None, f"{term}: HTTP {r.status_code}"
    r.encoding = "utf-8"
    return url, r.text, ""


def main(domain, brand, alts):
    terms = [brand] + alts
    rx = re.compile("|".join(rf"(?<!\w){re.escape(t)}(?!\w)" for t in terms) + "|" + re.escape(domain), re.I)
    seen, items, errs, raw = set(), [], [], 0
    ctx = site_stems(domain, terms)
    for term in terms:
        url, xml, err = feed(term)
        if err:
            errs.append(err)
            continue
        for b in re.findall(r"<item>(.*?)</item>", xml, re.S):
            raw += 1
            title_full = tag(b, "title")
            src = re.search(r'<source url="([^"]*)"[^>]*>(.*?)</source>', b, re.S)
            publisher = html.unescape(src.group(2)).strip() if src else ""
            host = src.group(1) if src else ""
            headline = title_full[: -len(publisher) - 3] if publisher and title_full.endswith(f" - {publisher}") else title_full
            key = re.sub(r"\W+", " ", headline.lower()).strip()
            if key in seen or not rx.search(headline):
                continue
            seen.add(key)
            try:
                d = parsedate_to_datetime(tag(b, "pubDate")).date().isoformat()
            except Exception:
                d = None
            link = tag(b, "link")
            items.append({"type": "mention", "text": clean(headline, 240), "quote": " ".join(headline.split()[:25]),
                          "url": link, "date": d,
                          "meta": {"publisher": publisher, "publisher_url": host, "kind": kind_of(publisher, host),
                                   "query": term, "link_type": "google_news_redirect",
                                   "possible_homonym": bool(ctx) and not (stems(headline, terms) & ctx)}})
    items.sort(key=lambda i: i["date"] or "", reverse=True)
    if not items:
        status = "unavailable" if errs and not raw else "partial"
        return write_source(domain, "news", status, [], f"terms {terms}; {raw} raw RSS items, none with the brand in the headline; {'; '.join(errs)}")
    homonyms = [i for i in items if i["meta"]["possible_homonym"]]
    core = [i for i in items if not i["meta"]["possible_homonym"]]
    months = Counter((i["date"] or "")[:7] for i in core)
    today = date.today()
    seq = []
    for k in range(11, -1, -1):
        y, m = divmod(today.year * 12 + today.month - 1 - k, 12)
        seq.append(f"{y}-{m + 1:02d}")
    per_month = {m: months.get(m, 0) for m in seq}
    pubs = Counter(i["meta"]["publisher"] for i in core if i["meta"]["publisher"]).most_common(5)
    kinds = Counter(i["meta"]["kind"] for i in core)
    items.append({"type": "metric",
                  "text": f"{len(core)} headlines naming {brand} in 12 months ({len(homonyms)} more flagged as possible namesake companies); per month {per_month}; top publishers "
                          + ", ".join(f"{p} ({n})" for p, n in pubs) + f"; kinds {dict(kinds)}",
                  "url": f"https://news.google.com/search?q=%22{quote_plus(brand)}%22%20when%3A1y",
                  "meta": {"per_month": per_month, "top_publishers": pubs, "kinds": dict(kinds)}})
    note = (f"terms {terms}; Google News RSS 365d, {raw} raw items, {len(items) - 1} kept (brand in headline, deduped by title), {len(homonyms)} flagged possible_homonym (no overlap with site vocabulary, excluded from the metric); "
            "links are Google News redirects, publisher in meta; Google News returns a capped, relevance-ranked sample, not full coverage"
            + (f"; errors {errs}" if errs else ""))
    return write_source(domain, "news", "partial" if errs else "ok", items, note)


if __name__ == "__main__":
    main(*args_brand())
