"""Collector 11 — community talk: Hacker News (Algolia), Reddit search, Product Hunt page.

Keeps only hits that mention the brand or domain as a whole word (no false positives from a brand name split into two words);
hits with no vocabulary overlap with the company's own site are flagged possible_homonym and left out of the metrics.
Reddit JSON is often 403/429 for scripts; the Atom search feed is tried once as a fallback, otherwise partial.
Product Hunt sits behind a bot wall; it is recorded as unavailable when blocked.

Usage: python collectors/community.py example.com [--brand "Example"] [--alt "Old Name"]
"""
import argparse
import html
import re
import time
from datetime import date, datetime, timedelta, timezone

from common import SESSION, clean, write_source
from news import site_stems, stems

HN_API = "https://hn.algolia.com/api/v1/search_by_date"
MONTHS_BACK = 24


def args_brand():
    ap = argparse.ArgumentParser()
    ap.add_argument("domain")
    ap.add_argument("--brand")
    ap.add_argument("--alt", action="append", default=[])
    a = ap.parse_args()
    brand = a.brand or a.domain.split(".")[0].capitalize()
    return a.domain, brand, a.alt


def brand_rx(domain, terms):
    parts = [rf"(?<![\w]){re.escape(t)}(?![\w])" for t in terms] + [re.escape(domain)]
    return re.compile("|".join(parts), re.I)


def strip_html(s):
    return clean(html.unescape(re.sub(r"<[^>]+>", " ", s or "")))


def words_around(text, rx, n=25):
    """Verbatim window of at most n words that contains the first brand mention."""
    m = rx.search(text)
    if not m:
        return " ".join(text.split()[:n])
    before = len(text[:m.start()].split())
    words = text.split()
    start = max(0, min(before - n // 3, len(words) - n))
    return " ".join(words[start:start + n])


def hn_items(domain, terms, rx):
    since = int((datetime.now(timezone.utc) - timedelta(days=30 * MONTHS_BACK)).timestamp())
    seen, items, err = set(), [], ""
    for term in dict.fromkeys(terms):
        for page in range(6):
            try:
                r = SESSION.get(HN_API, params={"query": f'"{term}"', "tags": "(story,comment)", "page": page,
                                                "hitsPerPage": 100,
                                                "numericFilters": f"created_at_i>{since}"}, timeout=25)
                if r.status_code != 200:
                    err = f"HN HTTP {r.status_code}"
                    break
                j = r.json()
            except Exception as e:
                err = f"HN error {type(e).__name__}"
                break
            for h in j.get("hits", []):
                oid = h.get("objectID")
                if oid in seen:
                    continue
                title = h.get("title") or h.get("story_title") or ""
                body = strip_html(h.get("comment_text") or h.get("story_text") or "")
                blob = " ".join([title, body, h.get("url") or ""])
                if not rx.search(blob):
                    continue
                seen.add(oid)
                is_story = "story" in (h.get("_tags") or [])
                text = title if is_story and title else " ".join(body.split()[:30])
                quote = words_around(body or title, rx)
                items.append({
                    "type": "mention",
                    "text": clean(text.replace(" — ", ", ").replace("—", ", "), 240) or title,
                    "quote": quote,
                    "url": f"https://news.ycombinator.com/item?id={oid}",
                    "date": (h.get("created_at") or "")[:10],
                    "meta": {"platform": "hn", "points": h.get("points") or 0,
                             "num_comments": h.get("num_comments") or 0,
                             "kind": "story" if is_story else "comment",
                             "thread": h.get("story_title") if not is_story else None},
                })
            if page + 1 >= j.get("nbPages", 0):
                break
    return items, err


def reddit_items(brand, rx):
    """Returns (items, status_note). JSON first, Atom feed once as the single fallback."""
    q = f'"{brand}"'
    url = "https://www.reddit.com/search.json"
    try:
        r = SESSION.get(url, params={"q": q, "sort": "new", "t": "year", "limit": 50}, timeout=25)
    except Exception as e:
        return [], f"Reddit request failed ({type(e).__name__})"
    if r.status_code == 200:
        try:
            posts = [c["data"] for c in r.json()["data"]["children"]]
        except Exception:
            return [], "Reddit JSON not parsed"
        items = []
        for p in posts:
            blob = " ".join([p.get("title", ""), p.get("selftext", ""), p.get("url", "")])
            if not rx.search(blob):
                continue
            body = clean(p.get("selftext", ""))
            items.append({
                "type": "mention", "text": clean(p.get("title", ""), 240),
                "quote": words_around(body or p.get("title", ""), rx),
                "url": "https://www.reddit.com" + p.get("permalink", ""),
                "date": datetime.fromtimestamp(p.get("created_utc", 0), timezone.utc).strftime("%Y-%m-%d"),
                "meta": {"platform": "reddit", "subreddit": p.get("subreddit"), "score": p.get("score"),
                         "num_comments": p.get("num_comments")}})
        return items, ""
    first = f"Reddit JSON HTTP {r.status_code}"
    time.sleep(3)
    try:
        r2 = SESSION.get("https://www.reddit.com/search.rss", params={"q": q, "sort": "new", "t": "year"}, timeout=25)
    except Exception as e:
        return [], f"{first}; Atom fallback failed ({type(e).__name__})"
    if r2.status_code != 200 or "<entry" not in r2.text:
        return [], f"{first}; Atom fallback HTTP {r2.status_code}"
    items = []
    for e in re.findall(r"<entry>(.*?)</entry>", r2.text, re.S):
        title = html.unescape((re.search(r"<title>(.*?)</title>", e, re.S) or [0, ""])[1])
        link = (re.search(r'<link href="([^"]+)"', e) or [0, ""])[1]
        upd = (re.search(r"<updated>(.*?)</updated>", e) or [0, ""])[1][:10]
        sub = (re.search(r'<category term="([^"]+)"', e) or [0, ""])[1]
        body = strip_html(html.unescape((re.search(r"<content[^>]*>(.*?)</content>", e, re.S) or [0, ""])[1]))
        if not link or not rx.search(title + " " + body):
            continue
        items.append({"type": "mention", "text": clean(title, 240), "quote": words_around(body or title, rx),
                      "url": link, "date": upd,
                      "meta": {"platform": "reddit", "subreddit": sub, "score": None, "num_comments": None,
                               "via": "atom_feed"}})
    return items, f"{first}; used Atom search feed (no score or comment counts)"


def product_hunt(slugs):
    notes = []
    for slug in dict.fromkeys(slugs):
        url = f"https://www.producthunt.com/products/{slug}"
        try:
            r = SESSION.get(url, timeout=25)
        except Exception as e:
            notes.append(f"{slug}: {type(e).__name__}")
            continue
        if r.status_code != 200:
            notes.append(f"{slug}: HTTP {r.status_code}")
            continue
        m = re.search(r'"reviewsCount":\s*(\d+)', r.text)
        t = re.search(r"<title>(.*?)</title>", r.text, re.S)
        return [{"type": "page", "text": f"Product Hunt page: {clean(html.unescape(t.group(1)), 120) if t else slug}",
                 "quote": "", "url": url,
                 "meta": {"platform": "producthunt", "reviews": int(m.group(1)) if m else None}}], ""
    return [], "Product Hunt unavailable (" + ", ".join(notes) + ")"


def eng(i):
    m = i["meta"]
    return (m.get("points") or m.get("score") or 0) + (m.get("num_comments") or 0)


def flag_homonyms(items, ctx, terms):
    """Mark hits sharing no vocabulary with the company's own site (namesake companies, unrelated hobby threads)."""
    for i in items:
        blob = " ".join([i["text"], i.get("quote") or "", str(i["meta"].get("subreddit") or ""), str(i["meta"].get("thread") or "")])
        i["meta"]["possible_homonym"] = bool(ctx) and not (stems(blob, terms) & ctx)


def summary(platform, items, search_url):
    cutoff = (date.today() - timedelta(days=365)).isoformat()
    last = [i for i in items if (i.get("date") or "") >= cutoff and not i["meta"].get("possible_homonym")]
    has_eng = any(eng(i) for i in last)
    top = sorted(last, key=eng, reverse=True)[:3] if has_eng else sorted(last, key=lambda i: i.get("date") or "", reverse=True)[:3]
    label = "top 3 by engagement" if has_eng else "engagement not available, 3 most recent"
    top_txt = "; ".join(f"{clean(i['text'], 60)}" + (f" [{eng(i)}]" if has_eng else "") for i in top) or "none"
    return {"type": "metric", "text": f"{platform}: {len(last)} brand mentions in the last 12 months ({len(items)} hits in window, {sum(bool(i['meta'].get('possible_homonym')) for i in items)} flagged possible_homonym and excluded); {label}: {top_txt}",
            "url": search_url, "meta": {"platform": platform, "mentions_12m": len(last), "hits_total": len(items),
                                        "top3": [{"url": i["url"], "engagement": eng(i)} for i in top]}}


def main(domain, brand, alts):
    terms = [brand] + alts
    rx = brand_rx(domain, terms)
    hn, hn_err = hn_items(domain, terms, rx)
    rd, rd_note = reddit_items(brand, rx)
    ph, ph_note = product_hunt([domain.split(".")[0], re.sub(r"[^a-z0-9]+", "-", brand.lower()).strip("-")])
    ctx = site_stems(domain, terms)
    flag_homonyms(hn, ctx, terms)
    flag_homonyms(rd, ctx, terms)
    items = []
    keep = sorted(hn, key=lambda i: (eng(i), i["date"]), reverse=True)[:120]
    items += sorted(keep, key=lambda i: i["date"], reverse=True)
    items += rd + ph
    items.append(summary("Hacker News", hn, f"https://hn.algolia.com/?q={brand}&dateRange=pastYear&type=all"))
    if rd:
        items.append(summary("Reddit", rd, f"https://www.reddit.com/search/?q=%22{brand}%22&sort=new&t=year"))
    for i in items:  # normalized text carries no dashes used as punctuation; quotes stay verbatim
        i["text"] = i["text"].replace(" — ", ", ").replace("—", ", ")
    ok_parts = sum(bool(x) for x in (hn, rd, ph))
    status = "ok" if hn and rd and ph else ("partial" if ok_parts else "unavailable")
    note = (f"terms {terms}; HN Algolia 24 months, word-boundary filter, {len(hn)} hits (window 6x100 pages per term)"
            f"{'; ' + hn_err if hn_err else ''}; Reddit {len(rd)} hits{'; ' + rd_note if rd_note else ''}; "
            f"Product Hunt {'found' if ph else ph_note}")
    return write_source(domain, "community", status, items, note)


if __name__ == "__main__":
    main(*args_brand())
