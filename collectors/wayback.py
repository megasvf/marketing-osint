"""Collector 2 - Wayback: home + pricing snapshots ~3, 6, 9 and 12 months ago vs today (quarterly history).

Usage: python collectors/wayback.py example.com
"""
import json
import sys
import time
from datetime import date, timedelta

from common import ROOT, SESSION, fetch, page_signals, write_source

CDX = "https://web.archive.org/cdx/search/cdx"


def closest(url, target):
    """Closest 200 snapshot to target date via CDX; returns (timestamp, archived_url) or None."""
    ts = target.strftime("%Y%m%d")
    for attempt in range(3):
        hit = _closest_once(url, target, ts)
        if hit:
            return hit
        time.sleep(6)
    return None


def _closest_once(url, target, ts):
    try:
        r = SESSION.get(CDX, params={"url": url, "output": "json", "filter": "statuscode:200",
                                     "from": (target - timedelta(days=45)).strftime("%Y%m%d"),
                                     "to": (target + timedelta(days=45)).strftime("%Y%m%d"),
                                     "fl": "timestamp", "collapse": "timestamp:8", "limit": 60},
                        timeout=40)
        rows = r.json()[1:]
    except Exception:
        return None
    if not rows:
        return None
    best = min(rows, key=lambda x: abs(int(x[0][:8]) - int(ts)))[0]
    return best, f"https://web.archive.org/web/{best}id_/{url}"


def snap_items(label, page, when, arch_url, s):
    items = [{"type": "change", "text": f"{page} {label}: title", "quote": s["title"], "url": arch_url,
              "date": when, "meta": {"page": page, "when": label, "field": "title"}},
             {"type": "change", "text": f"{page} {label}: meta description", "quote": s["description"][:200],
              "url": arch_url, "date": when, "meta": {"page": page, "when": label, "field": "description"}}]
    for h in (s["h1"][:2] + s["h2"][:8]):
        items.append({"type": "change", "text": f"{page} {label}: heading", "quote": h, "url": arch_url,
                      "date": when, "meta": {"page": page, "when": label, "field": "heading"}})
    return items


def resolved_pricing(domain):
    """Pricing URL as resolved by the site collector (may live on a sibling domain)."""
    try:
        site = json.loads((ROOT / "data" / domain / "site.json").read_text(encoding="utf-8"))
        for i in site["items"]:
            if i["meta"].get("kind") == "pricing" and i["type"] == "page":
                return i["url"]
    except (OSError, KeyError, ValueError):
        pass
    return f"https://{domain}/pricing"


def main(domain):
    today = date.today()
    items, misses = [], []
    for page, url in (("home", f"https://{domain}/"), ("pricing", resolved_pricing(domain))):
        path = url.split("://", 1)[1]
        fu, html = fetch(url)
        if html:
            items += snap_items("now", page, today.isoformat(), fu, page_signals(html, fu))
        for label, days in (("3mo_ago", 91), ("6mo_ago", 182), ("9mo_ago", 274), ("12mo_ago", 365)):
            hit = closest(path, today - timedelta(days=days))
            time.sleep(1.5)
            if not hit:
                misses.append(f"{page}/{label}")
                continue
            ts, arch = hit
            fu, h = fetch(arch, timeout=40)
            if not h:
                time.sleep(6)
                fu, h = fetch(arch, timeout=60)
            if not h:
                misses.append(f"{page}/{label}")
                continue
            when = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
            items += snap_items(label, page, when, f"https://web.archive.org/web/{ts}/{url}", page_signals(h, url))
    status = "ok" if not misses else ("partial" if items else "unavailable")
    return write_source(domain, "wayback", status, items, f"missing snapshots: {misses}")


if __name__ == "__main__":
    main(sys.argv[1])
