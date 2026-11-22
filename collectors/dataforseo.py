"""Collector — DataForSEO: one pay-as-you-go account for SEO, backlinks, SERPs and AI answers.

Test replacement for the Ahrefs agent collectors and the per-model AI keys. Writes three files so a run
can be compared side by side with the Ahrefs ones (different models: never mix them in one series):
  data/<domain>/dfs_seo.json        Labs: snapshot, 24-month history, top pages, top keywords, paid, competitors, keyword gap
  data/<domain>/dfs_backlinks.json  Backlinks: summary (rank 0-100), 24-month history, newest referring domains, anchors
  data/<domain>/dfs_ai.json         AI Optimization LLM Responses: the 10 ai_visibility prompts per platform, web search on

Auth: env DATAFORSEO_LOGIN + DATAFORSEO_PASSWORD (API credentials from app.dataforseo.com/api-access).
Every response carries `cost`; the sum is logged with costs.py. Prices (2026-11-22, dataforseo.com/pricing):
Labs $0.012/task + $0.00012/item (historical_rank_overview $0.12 + $0.0012/month), Backlinks $0.024/task +
$0.000036/row, SERP live $0.002, LLM Responses live $0.0006 + the model's own token and search charge.

Usage: python collectors/dataforseo.py example.com --brand Example --category "form builder" --competitor rival.com
       [--platforms chat_gpt,gemini,perplexity] [--skip-ai] [--dry-run]
Models: the first model with web search from each platform's models list; override with env
DFS_MODEL_CHAT_GPT / DFS_MODEL_GEMINI / DFS_MODEL_PERPLEXITY / DFS_MODEL_CLAUDE.
"""
import argparse
import base64
import json
import os
import re
import sys
from datetime import date

import requests

from common import ROOT, write_source

sys.path.insert(0, str(ROOT))
import costs  # noqa: E402
from ai_visibility import PROMPTS  # noqa: E402  (same prompts, so answers compare like for like)

API = "https://api.dataforseo.com/v3"
US = {"location_code": 2840, "language_code": "en"}
SPENT = {"seo": 0.0, "backlinks": 0.0, "ai": 0.0}


def auth():
    login, pw = os.environ.get("DATAFORSEO_LOGIN", ""), os.environ.get("DATAFORSEO_PASSWORD", "")
    if not (login and pw):
        return None
    return {"Authorization": "Basic " + base64.b64encode(f"{login}:{pw}".encode()).decode(),
            "Content-Type": "application/json"}


def call(path, task, bucket, hdr, timeout=180):
    """POST one task; returns (result list or None, error text). Never echoes credentials."""
    try:
        r = requests.post(f"{API}{path}", headers=hdr, json=[task], timeout=timeout)
        d = r.json()
    except (requests.RequestException, ValueError) as e:
        return None, f"{path}: {type(e).__name__}"
    SPENT[bucket] += float(d.get("cost") or 0)
    t = (d.get("tasks") or [{}])[0]
    if t.get("status_code") != 20000:
        return None, f"{path}: {t.get('status_code')} {t.get('status_message')}"
    return t.get("result") or [], ""


def get(path, hdr):
    try:
        d = requests.get(f"{API}{path}", headers=hdr, timeout=60).json()
        return ((d.get("tasks") or [{}])[0].get("result") or []), ""
    except (requests.RequestException, ValueError) as e:
        return None, f"{path}: {type(e).__name__}"


def labs_url(domain):
    return f"https://app.dataforseo.com/?target={domain}"


def seo(domain, brand, competitor, hdr):
    items, notes = [], []
    url = labs_url(domain)
    today = date.today()
    start = date(today.year - 2, today.month, 1).isoformat()

    res, err = call("/dataforseo_labs/google/domain_rank_overview/live", {"target": domain, **US}, "seo", hdr)
    if res:
        m = ((res[0].get("items") or [{}])[0].get("metrics") or {})
        o, p = m.get("organic") or {}, m.get("paid") or {}
        items.append({"type": "metric", "text": f"Snapshot (US, Labs): estimated organic traffic {round(o.get('etv') or 0):,}, "
                      f"{o.get('count', 0):,} organic keywords, {(o.get('pos_1') or 0) + (o.get('pos_2_3') or 0):,} in the top 3; "
                      f"{p.get('count', 0):,} paid keywords", "url": url, "meta": {"metric": "snapshot", "organic": o, "paid": p}})
    elif err:
        notes.append(err)

    res, err = call("/dataforseo_labs/google/historical_rank_overview/live",
                    {"target": domain, **US, "date_from": start, "correlate": True}, "seo", hdr)
    if res:
        pts = [{"date": f"{x.get('year')}-{x.get('month'):02d}-01",
                "organic_etv": round((x.get("metrics") or {}).get("organic", {}).get("etv") or 0),
                "organic_keywords": (x.get("metrics") or {}).get("organic", {}).get("count"),
                "paid_etv": round((x.get("metrics") or {}).get("paid", {}).get("etv") or 0)}
               for x in (res[0].get("items") or []) if x.get("year")]
        pts.sort(key=lambda r: r["date"])
        for key in ("organic_etv", "organic_keywords", "paid_etv"):
            items.append({"type": "series", "text": f"Monthly {key.replace('_', ' ')} (US, Labs), {len(pts)} months; current month partial",
                          "url": url, "meta": {"domain": domain, "metric": key,
                                               "points": [{"date": r["date"], "value": r[key]} for r in pts]}})
    elif err:
        notes.append(err)

    res, err = call("/dataforseo_labs/google/relevant_pages/live",
                    {"target": domain, **US, "limit": 30, "order_by": ["metrics.organic.etv,desc"]}, "seo", hdr)
    for x in ((res or [{}])[0].get("items") or []) if res else []:
        o = (x.get("metrics") or {}).get("organic") or {}
        items.append({"type": "page", "text": f"{x.get('page_address')}: estimated organic traffic {round(o.get('etv') or 0):,}",
                      "url": x.get("page_address") or url, "meta": {"etv": o.get("etv"), "keywords": o.get("count")}})
    if err:
        notes.append(err)

    brand_rx = re.compile(r"\b" + re.escape(brand.lower()) + r"\b")
    kw_lists = {}
    for target in [domain] + ([competitor] if competitor else []):
        res, err = call("/dataforseo_labs/google/ranked_keywords/live",
                        {"target": target, **US, "item_types": ["organic"], "limit": 100,
                         "order_by": ["ranked_serp_element.serp_item.etv,desc"]}, "seo", hdr)
        if err:
            notes.append(err)
        rows = []
        for x in ((res or [{}])[0].get("items") or []) if res else []:
            kd, se = x.get("keyword_data") or {}, (x.get("ranked_serp_element") or {}).get("serp_item") or {}
            rows.append({"keyword": kd.get("keyword"), "volume": (kd.get("keyword_info") or {}).get("search_volume"),
                         "pos": se.get("rank_group"), "etv": se.get("etv"), "url": se.get("url"),
                         "branded": bool(brand_rx.search((kd.get("keyword") or "").lower())) if target == domain else None})
        kw_lists[target] = rows
    own = kw_lists.get(domain) or []
    if own:
        tr = sum(r["etv"] or 0 for r in own)
        btr = sum(r["etv"] or 0 for r in own if r["branded"])
        items.append({"type": "metric", "text": f"Branded keywords: {sum(r['branded'] for r in own)} of the top {len(own)} US keywords, "
                      f"{100 * btr / tr:.1f}% of their estimated traffic (brand = keyword contains '{brand}')" if tr else "no traffic",
                      "url": url, "meta": {"metric": "brand_share", "branded_traffic": btr, "traffic": tr, "sample": len(own)}})
        for r in own[:50]:
            items.append({"type": "keyword", "text": f"{r['keyword']} (vol {r['volume']}, pos {r['pos']})", "url": r["url"] or url, "meta": r})
    if competitor and own and kw_lists.get(competitor):
        theirs = {r["keyword"]: r for r in kw_lists[competitor]}
        mine = {r["keyword"]: r for r in own}
        for k, r in sorted(((k, r) for k, r in mine.items() if k not in theirs and not r["branded"]), key=lambda t: -(t[1]["volume"] or 0))[:25]:
            items.append({"type": "keyword", "text": f"Gap, they win: {k} (vol {r['volume']}, pos {r['pos']})", "url": r["url"] or url,
                          "meta": {**r, "direction": "they_win", "basis": "not in the comparator's top 100 by traffic"}})
        for k, r in sorted(((k, r) for k, r in theirs.items() if k not in mine), key=lambda t: -(t[1]["volume"] or 0))[:25]:
            items.append({"type": "keyword", "text": f"Gap, {competitor} wins: {k} (vol {r['volume']}, pos {r['pos']})", "url": r["url"] or url,
                          "meta": {**r, "direction": "we_win", "basis": "not in the target's top 100 by traffic"}})

    res, err = call("/dataforseo_labs/google/relevant_pages/live",
                    {"target": domain, **US, "item_types": ["paid"], "limit": 20}, "seo", hdr)
    for x in ((res or [{}])[0].get("items") or []) if res else []:
        pm = (x.get("metrics") or {}).get("paid") or {}
        items.append({"type": "page", "text": f"Paid page {x.get('page_address')}: estimated paid traffic {round(pm.get('etv') or 0):,}",
                      "url": x.get("page_address") or url, "meta": {"paid": pm}})
    if err:
        notes.append(err)

    res, err = call("/dataforseo_labs/google/competitors_domain/live",
                    {"target": domain, **US, "limit": 10, "exclude_top_domains": True}, "seo", hdr)
    comps = [{"domain": x.get("domain"), "intersections": x.get("intersections"), "avg_position": x.get("avg_position")}
             for x in ((res or [{}])[0].get("items") or [])] if res else []
    if comps:
        items.append({"type": "metric", "text": "Organic competitors (US, Labs): " + ", ".join(c["domain"] for c in comps if c["domain"]),
                      "url": url, "meta": {"competitors": comps}})
    if err:
        notes.append(err)
    return items, notes


def backlinks(domain, hdr):
    items, notes, url = [], [], labs_url(domain)
    today = date.today()
    res, err = call("/backlinks/summary/live", {"target": domain, "rank_scale": "one_hundred", "include_subdomains": True}, "backlinks", hdr)
    if res:
        s = res[0]
        items.append({"type": "metric", "text": f"DataForSEO rank {s.get('rank')} (0-100, not Ahrefs DR); {s.get('referring_domains', 0):,} referring domains, "
                      f"{s.get('backlinks', 0):,} backlinks", "url": url,
                      "meta": {k: s.get(k) for k in ("rank", "backlinks", "referring_domains", "referring_main_domains", "backlinks_spam_score")}})
    elif err:
        notes.append(err)
    res, err = call("/backlinks/history/live", {"target": domain, "rank_scale": "one_hundred",
                                                "date_from": date(today.year - 2, today.month, 1).isoformat()}, "backlinks", hdr)
    rows = (res or [{}])[0].get("items") or [] if res else []
    for key in ("rank", "referring_domains"):
        if rows:
            items.append({"type": "series", "text": f"Monthly {key.replace('_', ' ')} (DataForSEO backlinks index)", "url": url,
                          "meta": {"domain": domain, "metric": f"dfs_{key}",
                                   "points": [{"date": (r.get("date") or "")[:7] + "-01", "value": r.get(key)} for r in rows]}})
    if err:
        notes.append(err)
    res, err = call("/backlinks/referring_domains/live", {"target": domain, "limit": 20, "order_by": ["first_seen,desc"]}, "backlinks", hdr)
    for x in ((res or [{}])[0].get("items") or []) if res else []:
        items.append({"type": "mention", "text": f"Referring domain {x.get('domain')} (rank {x.get('rank')}), first seen {(x.get('first_seen') or '')[:10]}",
                      "url": f"https://{x.get('domain')}/", "date": (x.get("first_seen") or "")[:10] or None, "meta": x})
    if err:
        notes.append(err)
    res, err = call("/backlinks/anchors/live", {"target": domain, "limit": 15, "order_by": ["backlinks,desc"]}, "backlinks", hdr)
    an = [{"anchor": x.get("anchor"), "backlinks": x.get("backlinks"), "referring_domains": x.get("referring_domains")}
          for x in ((res or [{}])[0].get("items") or [])] if res else []
    if an:
        items.append({"type": "metric", "text": "Top anchors: " + "; ".join(f"{a['anchor']} ({a['referring_domains']} domains)" for a in an[:8]),
                      "url": url, "meta": {"anchors": an}})
    if err:
        notes.append(err)
    return items, notes


def pick_model(platform, hdr):
    env = os.environ.get(f"DFS_MODEL_{platform.upper()}")
    if env:
        return env, ""
    res, err = get(f"/ai_optimization/{platform}/llm_responses/models", hdr)
    if not res:
        return None, err or f"{platform}: no models listed"
    ok = [m for m in res if m.get("web_search_supported")] or res
    return ok[0].get("model_name"), ""


def ai(domain, brand, category, platforms, hdr):
    items, notes, raw = [], [], []
    prompts = [p.format(category=category, brand=brand) for p in PROMPTS]
    brand_rx = re.compile(r"\b" + re.escape(brand) + r"\b", re.I)
    for plat in platforms:
        model, err = pick_model(plat, hdr)
        if not model:
            notes.append(err)
            continue
        hits = 0
        for i, q in enumerate(prompts):
            task = {"user_prompt": q[:500], "model_name": model, "max_output_tokens": 2048, "web_search": True}
            res, err = call(f"/ai_optimization/{plat}/llm_responses/live", task, "ai", hdr, timeout=300)
            if not res:
                notes.append(err)
                raw.append({"provider": plat, "model": model, "idx": i, "prompt": q, "error": err})
                continue
            it = (res[0].get("items") or [{}])[0]
            text = "\n".join(s.get("text", "") for s in ((it.get("message") or {}).get("sections") or []))
            cites = [a.get("url") for a in (it.get("annotations") or []) if a.get("url")]
            named = bool(brand_rx.search(text))
            hits += named and i < 6
            raw.append({"provider": plat, "model": model, "idx": i, "prompt": q, "text": text, "cites": cites,
                        "money_spent": res[0].get("money_spent"), "web_search": True})
        items.append({"type": "metric", "text": f"{plat} ({model}): {brand} named in {hits} of 6 brandless prompts (one run, web search on)",
                      "url": f"ai_answers.html#dfs-{plat}", "meta": {"provider": plat, "model": model, "hits": hits, "of": 6}})
    (ROOT / "data" / domain / "_dfs_ai_raw.json").write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
    return items, notes


def plan(args):
    n_kw = 2 if args.competitor else 1
    labs = 0.01212 + 0.1488 + 0.0156 + n_kw * 0.024 + 0.0144 + 0.0132
    bl = 0.024036 + 0.024864 + 0.02472 + 0.02454
    print(f"Planned: Labs 6+{n_kw - 1} calls ≈ ${labs:.3f}; Backlinks 4 calls ≈ ${bl:.3f}; "
          f"AI: {0 if args.skip_ai else 10 * len(args.platforms)} LLM calls at $0.0006 + model tokens and search (not fixed; docs examples $0.007-0.04 per call)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("domain")
    ap.add_argument("--brand", required=True)
    ap.add_argument("--category", required=True)
    ap.add_argument("--competitor", default="")
    ap.add_argument("--platforms", default="chat_gpt,gemini,perplexity")
    ap.add_argument("--skip-ai", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    a.platforms = [p.strip() for p in a.platforms.split(",") if p.strip()]
    plan(a)
    if a.dry_run:
        return
    hdr = auth()
    if not hdr:
        for src in ("dfs_seo", "dfs_backlinks") + (() if a.skip_ai else ("dfs_ai",)):
            write_source(a.domain, src, "unavailable", [], "DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD not set")
        return
    for src, fn in (("dfs_seo", lambda: seo(a.domain, a.brand, a.competitor, hdr)), ("dfs_backlinks", lambda: backlinks(a.domain, hdr))) + \
            (() if a.skip_ai else (("dfs_ai", lambda: ai(a.domain, a.brand, a.category, a.platforms, hdr)),)):
        items, notes = fn()
        status = "ok" if items and not notes else ("partial" if items else "unavailable")
        write_source(a.domain, src, status, items, "; ".join(notes)[:900])
    for bucket, usd in SPENT.items():
        if usd:
            costs.record(a.domain, f"DataForSEO {bucket}", round(usd, 4), "USD", "sum of response cost fields", billing="pay per use")
    print("DataForSEO spend:", {k: round(v, 4) for k, v in SPENT.items()}, "total", round(sum(SPENT.values()), 4))


if __name__ == "__main__":
    main()
