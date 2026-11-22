"""Monitor mode: snapshot collector data per run and diff against the previous snapshot.

  python monitor.py example.com            # snapshot today's data/<domain>/*.json, write changes.json + changes.md
  python monitor.py example.com --diff-only

Snapshots live in data/<domain>/history/<YYYY-MM-DD>/. The first run is a baseline (no changes).
changes.json feeds the "Since last run" block in build.py; changes.md is a short text to paste into a chat.
"""
import json

import report_charts as RC
import re
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def snap_dir(domain):
    return ROOT / "data" / domain / "history"


def snapshot(domain):
    src = ROOT / "data" / domain
    dst = snap_dir(domain) / date.today().isoformat()
    dst.mkdir(parents=True, exist_ok=True)
    for f in src.glob("*.json"):
        if not f.name.startswith("_") and f.name != "changes.json":
            shutil.copy2(f, dst / f.name)
    return dst


def load(d, name):
    f = d / f"{name}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def items(doc):
    return (doc or {}).get("items", [])


def pct(a, b):
    return (b - a) / a * 100 if a else None


def diff(old, new):
    ch = []

    def add(area, text, url, before=None, after=None):
        ch.append({"area": area, "text": text, "url": url, "before": before, "after": after})

    # headline + CTAs
    def heads(doc):
        out = {}
        for i in items(doc):
            k = i.get("meta", {}).get("kind")
            if k == "home" and i["type"] == "page":
                out["home title"] = (i["text"].split(": ", 1)[-1], i["url"])
            if k == "home" and i.get("meta", {}).get("level") == "h1":
                out.setdefault("home H1", (i["text"], i["url"]))
            if k == "pricing_body":
                prices = sorted(set(re.findall(r"[$€£]\s?\d[\d,.]*", i.get("quote", ""))))
                out["pricing prices"] = (", ".join(prices), i["url"])
        return out
    ho, hn = heads(load(old, "site")), heads(load(new, "site"))
    for k in hn:
        if k in ho and ho[k][0] != hn[k][0]:
            add("Messaging" if k != "pricing prices" else "Pricing", f"{k} changed", hn[k][1], ho[k][0], hn[k][0])
    ctas = lambda d: {i["text"] for i in items(d) if i["type"] == "cta" and i.get("meta", {}).get("kind") == "home"}
    co, cn = ctas(load(old, "site")), ctas(load(new, "site"))
    if co and cn and co != cn:
        add("Messaging", f"Home CTAs: +{sorted(cn - co)} -{sorted(co - cn)}", "", None, None)

    # ads per platform + new creatives
    def ads(doc):
        tot, urls = {}, set()
        for i in items(doc):
            m = i.get("meta", {})
            if "total_ads" in m:
                tot[m["platform"]] = max(tot.get(m["platform"], 0), RC.ad_count(m["total_ads"]) or 0)
            if i["type"] == "ad":
                urls.add(i["url"])
        return tot, urls
    (to, uo), (tn, un) = ads(load(old, "ad_libraries")), ads(load(new, "ad_libraries"))
    for p in tn:
        if p in to and to[p] != tn[p]:
            add("Paid", f"{p.title()} ads {to[p]} to {tn[p]}", "", to[p], tn[p])
    if un - uo and uo:
        add("Paid", f"{len(un - uo)} new LinkedIn creatives in the sample", sorted(un - uo)[0])

    # traffic
    def visits(doc):
        for i in items(doc):
            if "visits" in i.get("meta", {}):
                return i["meta"]["visits"], i["url"]
        return None, None
    (vo, _), (vn, url) = visits(load(old, "similarweb")), visits(load(new, "similarweb"))
    if vo and vn and abs(pct(vo, vn)) >= 5:
        add("Traffic", f"Monthly visits {vo:,} to {vn:,} ({pct(vo, vn):+.0f}%)", url, vo, vn)

    def org(doc):
        for i in items(doc):
            m = i.get("meta", {})
            if m.get("metric") == "organic_traffic" and m.get("points"):
                pts = [p for p in m["points"] if p["date"][:7] < date.today().strftime("%Y-%m")]
                return m.get("domain"), (pts[-1]["value"] if pts else None)
        return None, None
    (do_, oo), (dn, on) = org(load(old, "ahrefs_history")), org(load(new, "ahrefs_history"))
    if oo and on and abs(pct(oo, on)) >= 5:
        add("Traffic", f"Organic traffic {oo:,} to {on:,} ({pct(oo, on):+.0f}%)", "", oo, on)

    # AI visibility
    def ai(doc):
        return {i["meta"]["provider"]: (i["meta"]["hits"], i["meta"]["of"]) for i in items(doc) if "hits" in i.get("meta", {})}
    ao, an = ai(load(old, "ai_visibility")), ai(load(new, "ai_visibility"))
    for p in an:
        if p in ao and ao[p] != an[p]:
            add("AI visibility", f"{p}: named in {ao[p][0]}/{ao[p][1]} to {an[p][0]}/{an[p][1]} category prompts", "ai_answers.html")

    # stack, subdomains, jobs, mentions, sitemap buckets, ratings, github stars
    def tools(doc):
        return {i["meta"]["tool"] for i in items(doc) if i.get("meta", {}).get("tool")}
    so, sn = tools(load(old, "stack")), tools(load(new, "stack"))
    if so and (sn - so or so - sn):
        add("Stack", f"Tools added {sorted(sn - so)}, removed {sorted(so - sn)}", "")
    for name, area, typ in (("subdomains", "Launch signals", "change"), ("hiring", "Hiring", "job"),
                            ("news", "Press", "mention"), ("community", "Community", "mention")):
        uo_ = {i["url"] for i in items(load(old, name)) if i["type"] == typ}
        new_items = [i for i in items(load(new, name)) if i["type"] == typ and i["url"] not in uo_]
        if uo_ and new_items:
            add(area, f"{len(new_items)} new: " + "; ".join(i["text"][:60] for i in new_items[:3]), new_items[0]["url"])

    def buckets(doc):
        return {i["meta"]["bucket"]: i["meta"]["count"] for i in items(doc) if "bucket" in i.get("meta", {}) and "count" in i["meta"]}
    bo, bn = buckets(load(old, "sitemap")), buckets(load(new, "sitemap"))
    for b in bn:
        if b in bo and bo[b] and abs(pct(bo[b], bn[b])) >= 5:
            add("Content", f"Sitemap '{b}' pages {bo[b]} to {bn[b]}", "")

    def ratings(*docs):
        out = {}
        for d in docs:
            for i in items(d):
                m = i.get("meta", {})
                plat = m.get("platform") or m.get("marketplace")
                if plat and isinstance(m.get("rating"), (int, float)):
                    out.setdefault(plat, (m["rating"], m.get("review_count"), i["url"]))
        return out
    ro = ratings(load(old, "earned"), load(old, "marketplaces"))
    rn = ratings(load(new, "earned"), load(new, "marketplaces"))
    for p in rn:
        if p in ro and ro[p][:2] != rn[p][:2]:
            add("Reviews", f"{p}: {ro[p][0]} ({ro[p][1]}) to {rn[p][0]} ({rn[p][1]})", rn[p][2])
    return ch


def write_changes(domain, prev, cur, ch, baseline=False):
    out = {"domain": domain, "since": prev.name if prev else None, "until": cur.name, "baseline": baseline, "items": ch}
    (ROOT / "data" / domain / "changes.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    if baseline:
        md = f"{domain}: baseline snapshot {cur.name}, changes will show from the next run."
    elif not ch:
        md = f"{domain}: no notable changes {prev.name} to {cur.name}."
    else:
        md = f"{domain}: {len(ch)} changes {prev.name} to {cur.name}\n" + "\n".join(f"- [{c['area']}] {c['text']}" for c in ch[:12])
    (ROOT / "data" / domain / "changes.md").write_text(md, encoding="utf-8")
    print(md)


def main(domain, diff_only=False):
    cur = snap_dir(domain) / date.today().isoformat() if diff_only else snapshot(domain)
    snaps = sorted(p for p in snap_dir(domain).iterdir() if p.is_dir() and p.name < cur.name)
    if not snaps:
        return write_changes(domain, None, cur, [], baseline=True)
    prev = snaps[-1]
    write_changes(domain, prev, cur, diff(prev, cur))


if __name__ == "__main__":
    main(sys.argv[1], "--diff-only" in sys.argv)
