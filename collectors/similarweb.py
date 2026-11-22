"""Collector 6 — SimilarWeb traffic: visits trend, channel mix, countries, keywords, AI referrals.

Source: the SimilarWeb API on RapidAPI (similarweb-api-pro, endpoint /website-overview), 1 call per domain.
Key: env RAPIDAPI_KEY (no key = source "unavailable", the report shows it as a gap).
A raw answer <= 45 days old in data/_cache/similarweb/<domain>.json is reused (no new spend).

Usage: python collectors/similarweb.py example.com
"""
import http.client
import json
import os
import sys
from datetime import date, datetime

from common import ROOT, write_source

import sys as _sys
_sys.path.insert(0, str(ROOT))
import costs  # noqa: E402

API_HOST = "similarweb-api-pro.p.rapidapi.com"
CACHE_DIR = ROOT / "data" / "_cache" / "similarweb"
MAX_AGE_DAYS = 45


def from_cache(domain):
    f = CACHE_DIR / f"{domain}.json"
    if f.exists():
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("success"):
            snap = datetime.fromisoformat(d["snapshotDate"][:10]).date()
            if (date.today() - snap).days <= MAX_AGE_DAYS:
                return d, f"cache {f.name}"
    return None, ""


def live(domain):
    key = os.environ.get("RAPIDAPI_KEY", "").strip()
    if not key:
        return None, "RAPIDAPI_KEY not set"
    try:
        conn = http.client.HTTPSConnection(API_HOST, timeout=60)
        conn.request("GET", f"/website-overview?url={domain.lower()}",
                     headers={"x-rapidapi-key": key, "x-rapidapi-host": API_HOST})
        d = json.loads(conn.getresponse().read().decode("utf-8"))
    except (OSError, ValueError) as e:  # never echo the key
        return None, f"live call failed ({type(e).__name__})"
    if not d.get("success"):
        return None, "live call failed"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{domain}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return d, "live RapidAPI call"


def main(domain):
    d, how = from_cache(domain)
    if d:
        costs.record(domain, "SimilarWeb (RapidAPI)", 0, "calls", f"reused {how} (no new spend)", billing="cache")
    else:
        d, how = live(domain)
        if how != "RAPIDAPI_KEY not set":
            costs.record(domain, "SimilarWeb (RapidAPI)", 1, "calls", "website-overview endpoint")
    url = f"https://www.similarweb.com/website/{domain}/"
    if not d:
        return write_source(domain, "similarweb", "unavailable", [], how)
    em = d["engagementMetrics"]
    items = [{"type": "metric", "text": f"Monthly visits {em['visits']:,} ({em['period']['year']}-{em['period']['month']:02d})",
              "url": url, "meta": {"visits": em["visits"], "bounce": em.get("bounceRate"),
                                   "pages_per_visit": em.get("pageviewsPerVisit"),
                                   "avg_duration_s": em.get("averageVisitDurationSeconds")}}]
    trend = d.get("estimatedMonthlyVisits", [])
    if trend:
        items.append({"type": "metric", "text": "Visits trend: " + ", ".join(f"{t['date'][:7]} {t['visits']:,}" for t in trend),
                      "url": url, "meta": {"trend": trend}})
    src = d.get("traffic", {}).get("sources", [])
    total = sum(s["share"] for s in src)
    items.append({"type": "metric", "text": "Channel mix: " + ", ".join(f"{s['source']} {s['sharePercentage']:.1f}%" for s in src),
                  "url": url, "meta": {"sources": src, "share_sum": round(total, 3)}})
    countries = d.get("audience", {}).get("topCountries", [])
    items.append({"type": "metric", "text": "Top countries: " + ", ".join(f"{c['countryCode']} {c['sharePercentage']:.1f}%" for c in countries),
                  "url": url, "meta": {"countries": countries}})
    for k in d.get("traffic", {}).get("topKeywords", [])[:10]:
        items.append({"type": "keyword", "text": f"{k['name']} (vol {k.get('volume')}, cpc ${k.get('cpc')})",
                      "url": url, "meta": k})
    ai = d.get("aiAnalytics", {})
    if ai.get("totalAiVisits"):
        items.append({"type": "metric", "text": f"AI-referral visits {ai['totalAiVisits']:,}: " +
                      ", ".join(f"{p['name']} {p['sharePercentage']:.0f}%" for p in ai.get("platforms", [])),
                      "url": url, "meta": {"platforms": [{k: p[k] for k in ("name", "sharePercentage")} for p in ai.get("platforms", [])]}})
    note = f"{how}; snapshot {d['snapshotDate'][:10]}"
    status = "ok"
    if total < 0.9:
        status = "partial"
        note += f"; channel shares sum to {total:.0%}; missing channels, do not read 0% as zero spend"
    return write_source(domain, "similarweb", status, items, note)


if __name__ == "__main__":
    main(sys.argv[1])
