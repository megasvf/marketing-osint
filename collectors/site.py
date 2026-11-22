"""Collector 1 — owned site: home, pricing, product/features, customers, about, blog, changelog.

Usage: python collectors/site.py example.com
"""
import re
import sys
from collections import Counter

from common import clean, fetch, page_signals, write_source

KEYS = {
    "pricing": r"pric|plans",
    "product": r"product|feature|platform|solution|sdk|studio",
    "customers": r"customer|case-stud|success|stories",
    "about": r"about|company|mission",
    "blog": r"/blog/?$|/blog\b|resources",
    "changelog": r"changelog|release|what.?s-new|updates|product-news",
}
PROBES = {
    "pricing": ["/pricing", "/plans", "/plans-pricing"],
    "changelog": ["/changelog", "/release-notes", "/whats-new", "/product-updates", "/updates"],
    "customers": ["/customers", "/customer-stories", "/case-studies"],
}
MAX_PER_KIND ={"product": 4, "customers": 1, "about": 1, "pricing": 1, "blog": 1, "changelog": 1}


def pick_pages(home_url, links):
    chosen = {}
    for text, url in links:
        path = url.lower().split("?")[0]
        for kind, rx in KEYS.items():
            if re.search(rx, path) and path.rstrip("/") != home_url.lower().rstrip("/"):
                bucket = chosen.setdefault(kind, [])
                # prefer short (hub-level) paths
                if url not in bucket and path.count("/") <= 5:
                    bucket.append(url)
    for kind in chosen:
        chosen[kind] = sorted(chosen[kind], key=lambda u: (u.count("/"), len(u)))[:MAX_PER_KIND[kind]]
    return chosen


def items_for(kind, url, s):
    items = [{"type": "page", "text": f"{kind}: {s['title']}", "quote": s["description"][:200],
              "url": url, "meta": {"kind": kind}}]
    for h in s["h1"][:2]:
        items.append({"type": "claim", "text": h, "quote": h, "url": url, "meta": {"kind": kind, "level": "h1"}})
    for h in s["h2"][:12]:
        items.append({"type": "claim", "text": h, "quote": h, "url": url, "meta": {"kind": kind, "level": "h2"}})
    if kind in ("home", "pricing", "product"):
        for c in s["ctas"][:8]:
            items.append({"type": "cta", "text": c, "quote": c, "url": url, "meta": {"kind": kind}})
    if kind == "pricing":
        body = s["body_full"]
        m = re.search(r"[$€£]\s?\d", body)
        start = max(0, m.start() - 400) if m else 0
        items.append({"type": "page", "text": "pricing page body excerpt", "quote": body[start:start + 2500],
                      "url": url, "meta": {"kind": "pricing_body"}})
    if kind in ("blog", "changelog"):
        # titles of recent entries = link texts pointing deeper than the hub
        seen = []
        for text, u in s["links"]:
            if u.rstrip("/") != url.rstrip("/") and u.startswith(url.rstrip("/")) and len(text) > 25 and text not in seen:
                seen.append(text)
                items.append({"type": "post", "text": text, "quote": text, "url": u, "meta": {"kind": kind}})
            if len(seen) >= 20:
                break
    return items


def main(domain):
    home_url, html = fetch(f"https://{domain}/")
    if not html:
        return write_source(domain, "site", "unavailable", [], "home page fetch failed")
    s = page_signals(html, home_url)
    items = items_for("home", home_url, s)
    pages = pick_pages(home_url, s["links"])
    # direct probes for hubs not linked from home (fetch follows redirects, e.g. /pricing -> /plans-pricing)
    for kind, paths in PROBES.items():
        if kind in pages:
            continue
        for p in paths:
            fu, h = fetch(f"https://{domain}{p}")
            if h:
                pages[kind] = [fu]
                break
    failed = []
    for kind, urls in pages.items():
        for u in urls:
            fu, h = fetch(u)
            if not h:
                failed.append(u)
                continue
            items += items_for(kind, fu, page_signals(h, fu))
    # nav vocabulary = what the company files its offering under
    nav = Counter(t for t, _ in s["links"] if 2 < len(t) < 30)
    items.append({"type": "page", "text": "home navigation labels",
                  "quote": "; ".join(t for t, _ in nav.most_common(30)), "url": home_url,
                  "meta": {"kind": "nav"}})
    found = {k: len(v) for k, v in pages.items()}
    status = "ok" if "pricing" in pages and "product" in pages else "partial"
    note = f"pages found {found}; failed {len(failed)} {failed[:3]}"
    return write_source(domain, "site", status, items, note)


if __name__ == "__main__":
    main(sys.argv[1])
