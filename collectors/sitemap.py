"""Collector 12 - sitemap structure: what sections the site has, how big, how fresh, who it compares itself to.

robots.txt Sitemap lines (else /sitemap.xml, /sitemap_index.xml), follows sitemap indexes
(max 40 child sitemaps, 60k URLs, 20s timeout each, gzip ok). URLs are bucketed by path pattern.

Usage: python collectors/sitemap.py example.com
"""
import gzip
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from common import SESSION, fetch, write_source

MAX_CHILD, MAX_URLS, TIMEOUT = 40, 60000, 20
LOCALE_RX = re.compile(r"^[a-z]{2}(?:-[a-z]{2,4})?$", re.I)
CMP_RX = re.compile(r"-vs-|/vs/|/vs-|-vs$|compar|versus", re.I)
ALT_RX = re.compile(r"alternativ", re.I)
# first-segment buckets, checked in order
SEGMENTS = [
    ("templates", r"templates?|examples?|gallery"),
    ("integrations", r"integrations?|apps|connectors?|plugins?|partners?|marketplace"),
    ("use-cases", r"use-cases?|solutions?|industr(?:y|ies)|for|teams|personas?"),
    ("customers", r"customers?|case-stud(?:y|ies)|customer-stor(?:y|ies)|success-stor(?:y|ies)|stories"),
    ("docs/help", r"docs?|help|support|developers?|api|knowledge-?base|kb|learn-center|documentation"),
    ("legal", r"privacy|terms|legal|cookies?|gdpr|dpa|security|compliance|trust"),
    ("blog/resources", r"blog|resources?|guides?|articles?|learn|academy|ebooks?|webinars?|news|podcast|glossary|courses?"),
]
TOP_N_OTHER = 8


def get_bytes(url):
    try:
        r = SESSION.get(url, timeout=TIMEOUT)
        if r.status_code >= 400:
            return None
        b = r.content
        if b[:2] == b"\x1f\x8b":
            b = gzip.decompress(b)
        return b.decode("utf-8", "replace")
    except Exception:
        return None


def parse(xml):
    """Return ('index'|'urls', [(loc, lastmod)])."""
    kind = "index" if "<sitemapindex" in xml[:2000] else "urls"
    tag = "sitemap" if kind == "index" else "url"
    out = []
    for blk in re.findall(rf"<{tag}\b.*?</{tag}>", xml, re.S):
        loc = re.search(r"<loc>\s*(?:<!\[CDATA\[)?\s*(.*?)\s*(?:\]\]>)?\s*</loc>", blk, re.S)
        lm = re.search(r"<lastmod>\s*(.*?)\s*</lastmod>", blk, re.S)
        if loc:
            out.append((loc.group(1).replace("&amp;", "&"), lm.group(1)[:10] if lm else None))
    # malformed index: a <urlset> whose locs are all child sitemaps (e.g. '/template-sitemap.xml/')
    if kind == "urls" and out and all(re.search(r"sitemap[^/]*\.xml(\.gz)?/?$", u, re.I) for u, _ in out):
        kind = "index"
        out = [(u.rstrip("/") if u.rstrip("/").endswith((".xml", ".gz")) else u, lm) for u, lm in out]
    return kind, out


def find_roots(domain):
    roots = []
    for base in (f"https://{domain}", f"https://www.{domain}"):
        txt = get_bytes(base + "/robots.txt")
        if txt and "<html" not in txt[:300].lower():
            roots += re.findall(r"(?im)^\s*sitemap:\s*(\S+)", txt)
            if roots:
                return list(dict.fromkeys(roots)), f"{base}/robots.txt"
    for base in (f"https://{domain}", f"https://www.{domain}"):
        for p in ("/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml"):
            txt = get_bytes(base + p)
            if txt and ("<urlset" in txt[:2000] or "<sitemapindex" in txt[:2000]):
                return [base + p], "probe"
    return [], "none"


def classify(url):
    """Return (bucket, locale, first_segment)."""
    path = urlparse(url).path.lower()
    segs = [s for s in path.split("/") if s]
    locale = None
    if segs and LOCALE_RX.match(segs[0]) and (len(segs) > 1 or len(segs[0]) == 2):
        locale, segs = segs[0], segs[1:]
    rest = "/" + "/".join(segs)
    first = segs[0] if segs else ""
    if ALT_RX.search(rest):
        return "alternatives", locale, first
    if CMP_RX.search(rest):
        return "comparison", locale, first
    for name, rx in SEGMENTS:
        if re.fullmatch(rx, first):
            return name, locale, first
    if not segs:
        return "home", locale, ""
    return "other", locale, first


def competitor_from(url, brand):
    slug = [s for s in urlparse(url).path.split("/") if s][-1].lower()
    slug = re.sub(r"\.(html?|php)$", "", slug)
    parts = re.split(r"-vs-|-versus-|-vs$|^vs-", slug)
    cand = parts[-1] if len(parts) > 1 else slug
    if len(parts) > 1 and brand and brand in parts[-1] and brand not in parts[0]:
        cand = parts[0]
    cand = re.sub(r"\b(?:the|best|top|\d+|alternatives?|alternative|to|compare|comparison|and|or|free)\b", " ", cand.replace("-", " "))
    cand = re.sub(r"\b" + re.escape(brand) + r"\b", " ", cand) if brand else cand
    name = re.sub(r"\s+", " ", cand).strip().title()
    return name or slug


def main(domain):
    brand = domain.split(".")[0].lower()
    roots, via = find_roots(domain)
    if not roots:
        return write_source(domain, "sitemap", "unavailable", [], "no sitemap found via robots.txt or /sitemap.xml probes")
    urls, failed, queue, children = {}, [], [(r, 0) for r in roots], 0   # url -> (lastmod, sitemap_file)
    seen_maps = set()
    truncated = False
    while queue:
        batch, queue = queue, []
        todo = []
        for sm, depth in batch:
            if sm in seen_maps:
                continue
            seen_maps.add(sm)
            if depth > 0:
                if children >= MAX_CHILD:
                    truncated = True
                    continue
                children += 1
            todo.append((sm, depth))
        with ThreadPoolExecutor(6) as ex:
            texts = list(ex.map(lambda t: get_bytes(t[0]), todo))
        for (sm, depth), xml in zip(todo, texts):
            if not xml:
                failed.append(sm)
                continue
            kind, rows = parse(xml)
            if kind == "index" and depth < 2:
                queue += [(loc, depth + 1) for loc, _ in rows]
            else:
                for loc, lm in rows:
                    if len(urls) >= MAX_URLS:
                        truncated = True
                        break
                    urls.setdefault(loc, (lm, sm))
    if not urls:
        return write_source(domain, "sitemap", "unavailable", [], f"sitemaps found {roots} but no URLs parsed; failed {failed[:3]}")

    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
    buckets = defaultdict(list)
    locales = Counter()
    other_first = Counter()
    for u, (lm, sm) in urls.items():
        b, loc, first = classify(u)
        buckets[b].append((u, lm, sm))
        if loc:
            locales[loc] += 1
        if b == "other":
            other_first[first] += 1
    n = len(urls)
    items = []
    order = ["templates", "integrations", "blog/resources", "use-cases", "customers", "comparison", "alternatives",
             "docs/help", "legal", "home", "other"]
    for b in order:
        rows = buckets.get(b)
        if not rows:
            continue
        files = Counter(sm for _, _, sm in rows)
        meta = {"bucket": b, "count": len(rows), "share_pct": round(100 * len(rows) / n, 1),
                "examples": [r[0] for r in rows[:3]]}
        if b == "other":
            meta["top_sections"] = dict(other_first.most_common(TOP_N_OTHER))
        items.append({"type": "metric", "text": f"Sitemap bucket '{b}': {len(rows)} URLs ({meta['share_pct']}% of {n})",
                      "quote": rows[0][0], "url": files.most_common(1)[0][0], "meta": meta})
    if locales:
        items.append({"type": "metric",
                      "text": f"{len(locales)} locale prefixes in sitemap URLs, {sum(locales.values())} URLs ({round(100 * sum(locales.values()) / n)}%)",
                      "url": roots[0], "meta": {"bucket": "locales", "locales": dict(locales.most_common(25))}})
    # hreflang on home
    hu, hh = fetch(f"https://{domain}/")
    if hh:
        hl = sorted(set(re.findall(r'<link[^>]+hreflang=["\']([\w-]+)["\']', hh, re.I)))
        if hl:
            items.append({"type": "metric", "text": f"Home page declares {len(hl)} hreflang values: {', '.join(hl[:15])}",
                          "url": hu, "meta": {"bucket": "hreflang", "hreflang": hl}})
    # page items: comparison / alternatives
    pages = 0
    for b in ("comparison", "alternatives"):
        for u, lm, sm in buckets.get(b, [])[:40]:
            if pages >= 40:
                break
            name = competitor_from(u, brand)
            items.append({"type": "page", "text": f"{b.title()} page, subject parsed from slug (a competitor only if it is a brand): {name}",
                          "quote": urlparse(u).path, "url": u, "date": lm if lm and re.match(r"\d{4}-\d{2}-\d{2}$", lm) else None,
                          "meta": {"kind": b, "competitor": name, "mentions_brand": brand in u.lower(), "sitemap": sm}})
            pages += 1
    for it in items:
        if it.get("date") is None:
            it.pop("date", None)
    # lastmod recency per bucket
    dated = [(b, lm) for b, rows in buckets.items() for _, lm, _ in rows if lm and re.match(r"\d{4}-\d{2}-\d{2}$", lm)]
    lm_note = "no lastmod values in sitemap"
    if dated:
        distinct = len({lm for _, lm in dated})
        per = {}
        for b, rows in buckets.items():
            with_lm = [lm for _, lm, _ in rows if lm and re.match(r"\d{4}-\d{2}-\d{2}$", lm)]
            if with_lm:
                per[b] = {"recent_90d": sum(1 for x in with_lm if x >= cutoff), "with_lastmod": len(with_lm), "total": len(rows)}
        recent = sum(v["recent_90d"] for v in per.values())
        stamped = distinct <= 3 and len(dated) > 50
        top = sorted(per.items(), key=lambda kv: -kv[1]["recent_90d"])[:3]
        txt = (f"Content velocity: {recent} of {len(dated)} URLs with lastmod changed since {cutoff}; top buckets "
               + ", ".join(f"{b} {v['recent_90d']}" for b, v in top))
        if stamped:
            txt += f" (only {distinct} distinct lastmod dates, likely bulk-stamped, treat as weak evidence)"
        items.append({"type": "metric", "text": txt, "url": roots[0],
                      "meta": {"bucket": "lastmod_recency", "cutoff": cutoff, "per_bucket": per, "distinct_lastmod_dates": distinct}})
        lm_note = f"lastmod on {len(dated)}/{n} URLs, {distinct} distinct dates"
    status = "partial" if (failed or truncated) else "ok"
    note = (f"roots via {via}: {roots[:3]}; {len(seen_maps)} sitemap files read ({children} children, cap {MAX_CHILD}); {n} URLs "
            f"(cap {MAX_URLS}); {lm_note}")
    if truncated:
        note += "; caps hit, counts are a lower bound"
    if failed:
        note += f"; failed {len(failed)}: {failed[:3]}"
    return write_source(domain, "sitemap", status, items, note)


if __name__ == "__main__":
    main(sys.argv[1])
