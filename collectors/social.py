"""Collector 7 — organic social: profiles linked from the site + YouTube uploads via public RSS.

LinkedIn / X / Instagram / Facebook feeds are login-gated, so they are listed as profiles only.
(Ahrefs social-media tools need channels connected in the Ahrefs workspace; not used by default.)

Usage: python collectors/social.py example.com
"""
import json
import re
import sys
from datetime import date, timedelta

from common import SESSION, fetch, write_source

NETS = r"(youtube\.com|x\.com|twitter\.com|instagram\.com|facebook\.com|linkedin\.com|tiktok\.com)"


REL = {"s": 0, "m": 0, "h": 0, "d": 1, "w": 7, "mo": 30, "y": 365}


def approx_date(rel):
    """'4mo ago' / '2 weeks ago' -> approximate ISO date."""
    m = re.match(r"(\d+)\s*(mo|y|w|d|h|m|s)", (rel or "").replace("month", "mo").replace("year", "y")
                 .replace("week", "w").replace("day", "d").replace("hour", "h"))
    return (date.today() - timedelta(days=int(m.group(1)) * REL[m.group(2)])).isoformat() if m else None


def youtube_items(handle_url):
    """Parse the channel's /videos tab (ytInitialData lockupViewModel); public RSS is gone (404)."""
    try:
        h = SESSION.get(handle_url.rstrip("/") + "/videos", timeout=25, cookies={"SOCS": "CAI"}).text
        data = json.loads(re.search(r"var ytInitialData = (\{.*?\});</script>", h).group(1))
    except Exception:
        return [], f"{handle_url}: videos tab not parsed"
    vids = []

    def walk(o):
        if isinstance(o, dict):
            if "lockupViewModel" in o:
                lv = o["lockupViewModel"]
                md = lv.get("metadata", {}).get("lockupMetadataViewModel", {})
                parts = [p.get("text", {}).get("content") for r in
                         md.get("metadata", {}).get("contentMetadataViewModel", {}).get("metadataRows", [])
                         for p in r.get("metadataParts", [])]
                vids.append((lv.get("contentId"), md.get("title", {}).get("content"), parts))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(data)
    items, cutoff = [], (date.today() - timedelta(days=180)).isoformat()
    for vid, title, parts in vids:
        rel = next((p for p in parts if p and "ago" in p), None)
        views = next((p for p in parts if p and "ago" not in p), None)
        when = approx_date(rel)
        items.append({"type": "post", "text": f"YouTube: {title}", "quote": title,
                      "url": f"https://www.youtube.com/watch?v={vid}", "date": when,
                      "meta": {"platform": "youtube", "channel": handle_url, "views": views, "published": rel,
                               "in_180d": bool(when and when >= cutoff)}})
    recent = sum(i["meta"]["in_180d"] for i in items)
    items.append({"type": "metric", "text": f"YouTube {handle_url.rsplit('/', 1)[-1]}: {recent} of latest {len(vids)} uploads in the last 180 days",
                  "url": handle_url, "meta": {"platform": "youtube", "uploads_180d": recent}})
    return items, ""


def main(domain):
    home, html = fetch(f"https://{domain}/")
    urls = [m.group(0) for m in re.finditer(r"https?://(?:www\.)?" + NETS + r"/[^\"'<>\s?]+", html or "")]
    urls = [u for u in dict.fromkeys(urls) if not re.search(r"/tr$|/sharer|/intent|/share", u)]
    items, notes = [], []
    for u in urls:
        net = re.search(NETS, u).group(1)
        if net == "youtube.com":
            yi, err = youtube_items(u)
            items += yi
            if err:
                notes.append(err)
        else:
            items.append({"type": "metric", "text": f"Profile on {net} (feed login-gated, not collected)", "url": u,
                          "meta": {"platform": net, "gated": True}})
    yt = [i for i in items if i["type"] == "post"]
    status = "partial" if yt else ("unavailable" if not items else "partial")
    note = (f"profiles found {len(urls)}; YouTube uploads {len(yt)}; LinkedIn/X/IG/FB feeds login-gated. "
            + "; ".join(notes))
    return write_source(domain, "social", status, items, note)


if __name__ == "__main__":
    main(sys.argv[1])
