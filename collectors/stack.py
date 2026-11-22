"""Collector 11 - martech and ad-pixel stack: tracking pixels, analytics, CRM, chat, consent, billing.

Fetches home, pricing and one product page, extracts public Google Tag Manager container ids and
fetches each public container (gtm.js). Detection is regex on page HTML plus the container source.
Only public ids (pixel ids, GTM ids) are kept in the output.

Usage: python collectors/stack.py example.com
"""
import json
import re
import subprocess
import sys

from common import ROOT, SESSION, fetch, write_source

# tool -> (category, detection regex, optional id regexes; first capture group of each is an id)
TOOLS = {
    "Meta Pixel": ("ad pixel", r"fbq\s*\(|connect\.facebook\.net/[\w_]+/fbevents\.js|facebook\.com/tr[/?]",
                   [r"fbq\(\s*['\"]init['\"]\s*,\s*['\"](\d{6,})", r"facebook\.com/tr/?\?id=(\d{6,})"]),
    "LinkedIn Insight": ("ad pixel", r"_linkedin_partner_id|snap\.licdn\.com|px\.ads\.linkedin\.com",
                         [r"_linkedin_partner_id\s*=\s*['\"](\d+)", r"px\.ads\.linkedin\.com/collect/?\?pid=(\d+)"]),
    "Google Ads": ("ad pixel", r"AW-\d{6,}|googleadservices\.com|googleads\.g\.doubleclick\.net",
                   [r"(AW-\d{6,})"]),
    "TikTok Pixel": ("ad pixel", r"analytics\.tiktok\.com|ttq\.load|ttq\.track", [r"ttq\.load\(\s*['\"]([A-Z0-9]{8,})"]),
    "Reddit Pixel": ("ad pixel", r"redditstatic\.com/ads/pixel\.js|rdt\(\s*['\"]init['\"]|alb\.reddit\.com",
                     [r"rdt\(\s*['\"]init['\"]\s*,\s*['\"]([\w-]+)"]),
    "X (Twitter) Pixel": ("ad pixel", r"static\.ads-twitter\.com|twq\(\s*['\"](?:init|config)['\"]",
                          [r"twq\(\s*['\"](?:init|config)['\"]\s*,\s*['\"](\w+)"]),
    "Microsoft UET": ("ad pixel", r"bat\.bing\.com|UET\(|uetq", [r"\bti\s*:\s*['\"]?(\d{6,})"]),
    "Quora Pixel": ("ad pixel", r"a\.quora\.com/qevents\.js|qp\(\s*['\"]init['\"]",
                    [r"qp\(\s*['\"]init['\"]\s*,\s*['\"](\w+)"]),
    "Pinterest Tag": ("ad pixel", r"s\.pinimg\.com/ct/core\.js|pintrk\(", [r"pintrk\(\s*['\"]load['\"]\s*,\s*['\"](\d+)"]),
    "Google Analytics 4": ("analytics", r"\bG-[A-Z0-9]{8,12}\b", [r"\b(G-[A-Z0-9]{8,12})\b"]),
    "Hotjar": ("analytics", r"static\.hotjar\.com|hjSiteSettings|hj\(\s*['\"]identify", [r"hjid\s*[:=]\s*(\d+)", r"hotjar-(\d+)"]),
    "Microsoft Clarity": ("analytics", r"clarity\.ms/tag|clarity\(\s*['\"]", [r"clarity\.ms/tag/(\w+)"]),
    "FullStory": ("analytics", r"fullstory\.com|fs\.js|window\['_fs_org'\]", [r"_fs_org['\"\]]*\s*=\s*['\"]([\w-]+)"]),
    "Segment": ("analytics", r"cdn\.segment\.com|segment\.io|analytics\.load\(", []),
    "RudderStack": ("analytics", r"rudderstack\.com|rudderlabs\.com|rudderanalytics", []),
    "Amplitude": ("analytics", r"cdn\.amplitude\.com|amplitude\.getInstance|amplitude\.init", []),
    "Mixpanel": ("analytics", r"cdn\.mxpnl\.com|mixpanel\.init|api-js\.mixpanel\.com", []),
    "Heap": ("analytics", r"heapanalytics\.com|heap\.load\(", [r"heap\.load\(\s*['\"](\d+)"]),
    "HubSpot": ("CRM/MA", r"js\.hs-scripts\.com|js\.hsforms\.net|js\.hs-analytics\.net|hubspot\.com/embed|hbspt\.forms",
                [r"js\.hs-scripts\.com/(\d+)", r"hs-analytics\.net/analytics/\d+/(\d+)", r"portalId\s*[:=]\s*['\"]?(\d+)"]),
    "Marketo": ("CRM/MA", r"munchkin\.marketo\.net|Munchkin\.init|marketo\.com/js/forms2", [r"Munchkin\.init\(\s*['\"]([\w-]+)"]),
    "Pardot": ("CRM/MA", r"pi\.pardot\.com|piAId|pardot\.com/pd\.js", [r"piAId\s*=\s*['\"]?(\d+)"]),
    "Salesforce": ("CRM/MA", r"force\.com|salesforce\.com/|web-to-lead|webto\.salesforce", []),
    "Intercom": ("chat", r"widget\.intercom\.io|intercomSettings|js\.intercomcdn\.com", [r"app_id['\"]?\s*:\s*['\"](\w{8})['\"]"]),
    "Drift": ("chat", r"js\.driftt\.com|drift\.load\(|window\.drift\b", []),
    "Zendesk": ("chat", r"static\.zdassets\.com|zopim|zendesk\.com/embeddable", [r"ekr\?key=([\w-]+)"]),
    "Optimizely": ("experimentation", r"cdn\.optimizely\.com|optimizely\.com/js", [r"optimizely\.com/js/(\d+)"]),
    "VWO": ("experimentation", r"dev\.visualwebsiteoptimizer\.com|_vwo_code|vwo_\$", [r"account_id\s*[:=]\s*['\"]?(\d+)"]),
    "Google Optimize": ("experimentation", r"googleoptimize\.com|optimize\.js\?id=", [r"(OPT-\w+)"]),
    "Clearbit": ("ABM/intent", r"tag\.clearbitscripts\.com|reveal\.clearbit\.com|clearbit\.com/v\d/", []),
    "6sense": ("ABM/intent", r"j\.6sc\.co|6sc\.co|6sense\.com", []),
    "Demandbase": ("ABM/intent", r"tag\.demandbase\.com|demandbase\.com", []),
    "ZoomInfo": ("ABM/intent", r"ws\.zoominfo\.com|zoominfo\.com/pixel|js\.zi-scripts\.com", []),
    "Leadfeeder/Dealfront": ("ABM/intent", r"sc\.lfeeder\.com|lftracker|dealfront\.com", []),
    "Cookiebot": ("consent", r"consent\.cookiebot\.com|cookiebot\.com", [r"cbid=([\w-]{36})", r"data-cbid=['\"]([\w-]{36})"]),
    "OneTrust": ("consent", r"cdn\.cookielaw\.org|onetrust\.com|OptanonWrapper", [r"cookielaw\.org/(?:consent|scripttemplates)/([\w-]{36})"]),
    "Chili Piper": ("CRM/MA", r"chilipiper\.com|ChiliPiper", []),
    "Calendly": ("CRM/MA", r"assets\.calendly\.com|calendly\.com/", []),
    "PartnerStack": ("affiliate", r"partnerstack\.com|growsumo", []),
    "FirstPromoter": ("affiliate", r"firstpromoter\.com|fpr\(\s*['\"]", []),
    "Rewardful": ("affiliate", r"r\.wdfl\.co|rewardful\.com|rewardful\(", []),
    "Stripe": ("billing", r"js\.stripe\.com|checkout\.stripe\.com", []),
    "Paddle": ("billing", r"cdn\.paddle\.com|Paddle\.Setup|paddle\.com/paddle", []),
    "Chargebee": ("billing", r"js\.chargebee\.com|chargebee\.com", []),
}
GTM_RX = re.compile(r"\bGTM-[A-Z0-9]{4,8}\b")
PRODUCT_SKIP = re.compile(r"pricing|plans", re.I)


def snippet(text, m):
    a = max(0, m.start() - 40)
    s = re.sub(r"\s+", " ", text[a:m.end() + 60]).strip()
    words = s.split(" ")
    if a > 0 and len(words) > 1:
        words = words[1:]  # drop a word cut in half by the window
    s = " ".join(words[:25])
    # write keys of analytics SDKs are not needed for the evidence
    return re.sub(r"(analytics\.load\()\s*[\"'][\w-]+[\"']", r"\1<key omitted>", s)


def scan(text, url, found):
    """Add detections from one text blob (page html or gtm.js) into found {tool: record}."""
    for tool, (cat, rx, id_rx) in TOOLS.items():
        m = re.search(rx, text, re.I if tool in ("Salesforce", "Calendly") else 0)
        if not m:
            continue
        rec = found.setdefault(tool, {"category": cat, "ids": [], "quote": snippet(text, m), "url": url, "where": []})
        if url not in rec["where"]:
            rec["where"].append(url)
        for irx in id_rx:
            for im in re.finditer(irx, text):
                gid = im.group(1)
                if gid not in rec["ids"]:
                    rec["ids"].append(gid)


def gtm_via_doh(gurl):
    """Resolve the GTM host over DNS-over-HTTPS and fetch with curl --resolve; None on failure."""
    try:
        ans = SESSION.get("https://cloudflare-dns.com/dns-query", params={"name": "www.googletagmanager.com", "type": "A"},
                          headers={"accept": "application/dns-json"}, timeout=15).json().get("Answer", [])
        ip = next(a["data"] for a in ans if a.get("type") == 1)
        out = subprocess.run(["curl", "-s", "-m", "30", "--resolve", f"www.googletagmanager.com:443:{ip}", gurl],
                             capture_output=True, timeout=40)
        body = out.stdout.decode("utf-8", "ignore")
        return body if len(body) > 200 else None
    except Exception:
        return None


def pick_pages(domain):
    """home + pricing + one product page. Pricing/product urls come from site.json if collected."""
    pages = {"home": f"https://{domain}/"}
    sj = ROOT / "data" / domain / "site.json"
    if sj.exists():
        try:
            for it in json.loads(sj.read_text(encoding="utf-8")).get("items", []):
                kind = (it.get("meta") or {}).get("kind")
                if it.get("type") == "page" and kind in ("pricing", "product") and kind not in pages:
                    pages[kind] = it["url"]
        except Exception:
            pass
    return pages


def main(domain):
    pages = pick_pages(domain)
    found, gtm_ids, fetched, failed = {}, {}, [], []
    for kind, url in pages.items():
        fu, html = fetch(url)
        if not html:
            failed.append(url)
            continue
        fetched.append(fu)
        scan(html, fu, found)
        for g in GTM_RX.findall(html):
            gtm_ids.setdefault(g, fu)
    if not fetched:
        return write_source(domain, "stack", "unavailable", [], f"no page could be fetched ({failed})")
    if "pricing" not in pages:
        failed.append("pricing URL unknown (site.json missing or no pricing page)")
    if "product" not in pages:
        # fall back to one product-like link from home
        failed.append("product URL unknown")
    gtm_ok = 0
    for gid, src in gtm_ids.items():
        gurl = f"https://www.googletagmanager.com/gtm.js?id={gid}"
        try:
            r = SESSION.get(gurl, timeout=25)
            if r.status_code == 200 and len(r.text) > 200:
                gtm_ok += 1
                scan(r.text, gurl, found)
            else:
                failed.append(f"{gurl} HTTP {r.status_code}")
        except Exception as e:
            body = gtm_via_doh(gurl)  # local DNS sinkholes googletagmanager.com (ad blocker)
            if body:
                gtm_ok += 1
                scan(body, gurl, found)
                continue
            dns = "NameResolutionError" in repr(e)
            failed.append(f"{gurl} {'DNS lookup failed (googletagmanager.com may be blocked by the local network)' if dns else type(e).__name__}")
    items = []
    for gid, src in gtm_ids.items():
        items.append({"type": "metric", "text": f"Google Tag Manager detected (tag management: container {gid})",
                      "quote": gid, "url": src, "meta": {"tool": "Google Tag Manager", "category": "tag management", "ids": [gid]}})
    for tool, rec in found.items():
        items.append({"type": "metric", "text": f"{tool} detected ({rec['category']})", "quote": rec["quote"],
                      "url": rec["url"], "meta": {"tool": tool, "category": rec["category"], "ids": rec["ids"][:8],
                                                  "found_in": rec["where"][:4]}})
    pixels = sorted(t for t, r in found.items() if r["category"] == "ad pixel")
    items.append({"type": "metric",
                  "text": f"{len(pixels)} ad pixels present: " + (", ".join(pixels) if pixels else "none detected")
                          + " (retargeting-capable channels)",
                  "url": fetched[0], "meta": {"tool": "summary", "category": "ad pixel", "pixels": pixels,
                                              "tools_total": len(found), "gtm_containers": list(gtm_ids)}})
    status = "ok" if not failed else "partial"
    note = (f"pages scanned {fetched}; GTM containers {list(gtm_ids) or 'none'} ({gtm_ok} fetched); "
            f"regex detection on HTML and public gtm.js only, tags loaded after consent or by external scripts may be missed")
    if failed:
        note += f"; not fetched: {failed[:5]}"
    return write_source(domain, "stack", status, items, note)


if __name__ == "__main__":
    main(sys.argv[1])
