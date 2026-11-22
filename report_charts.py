"""Deterministic figures built straight from collector JSON (no LLM numbers).

Each builder returns HTML ('' when the source is missing) so a report degrades to fewer charts,
never to invented ones.
"""
import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import charts as C

ROOT = Path(__file__).resolve().parent


def load(domain, source):
    f = ROOT / "data" / domain / f"{source}.json"
    if not f.exists():
        return None
    d = json.loads(f.read_text(encoding="utf-8"))
    return d if d.get("status") != "unavailable" else None


def _series(domain, metric):
    """ahrefs_history series per domain for a metric, dropping the current (partial) month."""
    d = load(domain, "ahrefs_history")
    if not d:
        return []
    cur = date.today().strftime("%Y-%m")
    out = []
    for i in d["items"]:
        m = i.get("meta", {})
        if i["type"] == "series" and m.get("metric") == metric:
            pts = [(p["date"], p["value"]) for p in m.get("points", []) if p["date"][:7] < cur and p.get("value") is not None]
            out.append({"name": m.get("domain"), "points": pts, "url": i["url"]})
    return out


def dynamics(domain):
    figs = []
    labels = {"organic_traffic": ("Organic search traffic, monthly", ""),
              "organic_keywords": ("Ranking keywords, monthly", ""),
              "refdomains": ("Referring domains", "")}
    for metric, (title, unit) in labels.items():
        ser = _series(domain, metric)
        if ser:
            note = "Ahrefs estimates, last full month shown." if metric != "domain_rating" else "Ahrefs DR, 0 to 100."
            big = metric == "organic_traffic"
            figs.append(C.line(ser, title, unit, note=note, src=ser[0]["url"], height=220 if big else 230,
                               width=640 if big else 420))
    return figs


def headline_traffic(domain):
    ser = _series(domain, "organic_traffic")
    return C.line(ser, "Organic search traffic, last 24 months", note="Ahrefs estimates, last full month shown.",
                  src=ser[0]["url"]) if ser else ""


def traffic(domain):
    d = load(domain, "similarweb")
    if not d:
        return []
    by = {}
    for i in d["items"]:
        m = i.get("meta", {})
        if "sources" in m:
            by["sources"] = (m["sources"], m.get("share_sum"), i["url"])
        if "countries" in m:
            by["countries"] = (m["countries"], i["url"])
    figs = []
    if "sources" in by:
        src, total, url = by["sources"]
        rows = [(s["source"], s["sharePercentage"], None) for s in sorted(src, key=lambda s: -s["share"]) if s["share"] > 0]
        zero = [s["source"] for s in src if not s["share"]]
        note = "SimilarWeb." + (f" Shares sum to {total * 100:.0f}%." if total and total < 0.9 else "") + \
            (f" Not measured (shown as 0%): {', '.join(zero)}." if zero else "")
        figs.append(C.hbar(rows, "Visit sources (share of visits)", "%", note=note, src=url, domain_max=100))
    if "countries" in by:
        cs, url = by["countries"]
        figs.append(C.hbar([(c["countryCode"], c["sharePercentage"], None) for c in cs], "Top countries (share of visits)", "%",
                           note="SimilarWeb, latest month.", src=url))
    return figs


def sw_stats(domain):
    d = load(domain, "similarweb")
    if not d:
        return None
    for i in d["items"]:
        t = i.get("meta", {}).get("trend")
        if t and len(t) >= 2:
            a, b = t[0]["visits"], t[-1]["visits"]
            ch = (b - a) / a * 100 if a else 0
            return {"label": "Monthly visits", "value": C.fmt(b), "sub": f"{ch:+.0f}% vs {t[0]['date'][:7]}",
                    "trend": "up" if ch > 3 else ("down" if ch < -3 else "flat"), "href": i["url"]}
    return None


def ad_count(v):
    """Ad-library counts arrive as numbers or as rounded labels ('~2K', '1,200+', 'about 960'). None if unreadable."""
    if isinstance(v, (int, float)):
        return v
    m = re.search(r"([\d.,]+)\s*([kKmM]?)", str(v or ""))
    if not m:
        return None
    n = float(m.group(1).replace(",", ""))
    return int(n * {"k": 1e3, "m": 1e6}.get(m.group(2).lower(), 1))


def paid(domain):
    d = load(domain, "ad_libraries")
    if not d:
        return []
    figs = []
    plat = [(i["meta"]["platform"].title(), ad_count(i["meta"]["total_ads"]), None, i["url"]) for i in d["items"]
            if i["type"] == "metric" and ad_count((i.get("meta") or {}).get("total_ads")) is not None]
    agg = {}
    for p, n, _, url in plat:  # several metrics per platform (e.g. Google domain + advertiser): keep the max
        if p not in agg or n > agg[p][0]:
            agg[p] = (n, url)
    if agg:
        rows = sorted(((p, n, None) for p, (n, _) in agg.items()), key=lambda r: -r[1])
        figs.append(C.hbar(rows, "Ads found per ad library", note="Totals as listed by each library, often rounded; time windows differ between libraries.",
                           src=next(iter(agg.values()))[1]))
    themes = Counter(i["meta"].get("theme") for i in d["items"] if i["type"] == "ad" and i.get("meta", {}).get("theme"))
    if themes:
        def nice(t):
            words = t.replace("_", " ").split()
            fix = {"ai": "AI", "sdk": "SDK", "ed": "ed"}
            return " ".join(fix.get(w, w) for w in [words[0].capitalize()] + words[1:]).replace("Ai ", "AI ").replace("Sdk ", "SDK ")
        figs.append(C.hbar([(nice(t), n, None) for t, n in themes.most_common(8)], "Sampled ad creatives by theme",
                           note=f"{sum(themes.values())} unique creatives sampled; undated.", src=d["items"][0]["url"]))
        prom = Counter("Brand page" if i["meta"].get("promoter") == "brand" else "Employee / expert"
                       for i in d["items"] if i["type"] == "ad")
        figs.append(C.hbar([(k, n, None) for k, n in prom.most_common()], "Who fronts the ads", note="Thought-leader ads run under a person's name."))
    return figs


def ai(domain, brand):
    d = load(domain, "ai_visibility")
    if not d:
        return []
    figs = []
    per = [(i["text"].split(":")[0], 100 * i["meta"]["hits"] / i["meta"]["of"], f'{i["meta"]["hits"]} of {i["meta"]["of"]}')
           for i in d["items"] if i["type"] == "metric" and i.get("meta", {}).get("of")]
    if per:
        figs.append(C.hbar(per, f"{brand} named in category answers, by model", "%", domain_max=100, value_fmt=lambda v: f"{v:.0f}%",
                           note="Share of prompts that do not name the brand. Raw answers linked.", src="ai_answers.html"))
    for i in d["items"]:
        m = i.get("meta", {})
        if m.get("co_mentions"):
            rows = [(n, c, None) for n, c in m["co_mentions"][:10]]
            figs.append(C.hbar(rows, "Brands named most often in the same answers", highlight=brand, note="Count of answers.",
                               src="ai_answers.html"))
        if m.get("cited"):
            figs.append(C.hbar([(h, c, None) for h, c in m["cited"][:8]], "Domains the models cite most", highlight=domain.split(".")[0],
                               note="Citations across all answers with web search.", src="ai_answers.html"))
    return figs


def ai_stat(domain, brand):
    d = load(domain, "ai_visibility")
    if not d:
        return None
    rows = [i["meta"] for i in d["items"] if i["type"] == "metric" and i.get("meta", {}).get("of")]
    if not rows:
        return None
    hits, of = sum(r["hits"] for r in rows), sum(r["of"] for r in rows)
    return {"label": "AI answers naming it", "value": f"{100 * hits / of:.0f}%", "sub": f"{hits} of {of} category prompts",
            "trend": None, "href": "ai_answers.html"}


def content(domain):
    figs = []
    sm = load(domain, "sitemap")
    if sm:
        rows = [(i["meta"]["bucket"].replace("_", " ").capitalize(), i["meta"]["count"], f'{i["meta"].get("share_pct", "")}%')
                for i in sm["items"] if i["type"] == "metric" and "bucket" in i.get("meta", {}) and "count" in i["meta"]]
        figs.append(C.hbar(sorted(rows, key=lambda r: -r[1]), "Site pages by type (sitemap)", note="Where the content investment goes.",
                           src=sm["items"][0]["url"]))
    months = defaultdict(int)
    srcs = []
    for s in ("community", "news"):
        d = load(domain, s)
        if not d:
            continue
        srcs.append(s)
        for i in d["items"]:
            if i["type"] == "mention" and i.get("date") and not i.get("meta", {}).get("possible_homonym"):
                months[i["date"][:7]] += 1
    if months:
        today = date.today()
        keys = []
        y, m = today.year, today.month
        for _ in range(12):
            keys.append(f"{y}-{m:02d}")
            m -= 1
            if m == 0:
                y, m = y - 1, 12
        keys.reverse()
        figs.append(C.columns([(k, months.get(k, 0)) for k in keys], "Mentions per month (HN, Reddit, news)",
                              note="Homonyms excluded; samples, not full coverage."))
    rel = load(domain, "releases")
    if rel:
        bm = next((i["meta"]["by_month"] for i in rel["items"] if i.get("meta", {}).get("by_month")), None)
        if bm:
            keys = sorted(bm)[-12:]
            figs.append(C.columns([(k, bm[k]) for k in keys], "Product releases per month",
                                  note="Public changelog / release-notes entries; fixes and features counted alike.",
                                  src=next((i["url"] for i in rel["items"] if i.get("meta", {}).get("by_month")), None)))
    soc = load(domain, "social")
    if soc:
        vids = [i for i in soc["items"] if i["type"] == "post" and i.get("meta", {}).get("platform") == "youtube" and i.get("date")]
        if vids:
            by = Counter(v["date"][:7] for v in vids)
            keys = sorted(by)[-12:]
            figs.append(C.columns([(k, by[k]) for k in keys], "YouTube uploads per month (approximate dates)",
                                  note="From the channel's videos tab; dates derived from 'n months ago'."))
    return figs


def stack(domain):
    d = load(domain, "stack")
    if not d:
        return ""
    groups = defaultdict(list)
    for i in d["items"]:
        m = i.get("meta", {})
        if m.get("tool") and m.get("category") and m["tool"].lower() != "summary" and "tools_total" not in m:
            if m["tool"] not in groups[m["category"]]:
                groups[m["category"]].append(m["tool"])
    order = ["ad pixel", "analytics", "CRM/MA", "chat", "ABM/intent", "experimentation", "affiliate", "billing", "consent", "tag management"]
    g = {k.capitalize(): groups[k] for k in order if k in groups}
    g.update({k.capitalize(): v for k, v in groups.items() if k not in order})
    return C.chips(g, "Marketing stack seen on the site", note="Regex on page HTML and public GTM containers; consent-gated tags may be missing.")


def ratings(domain):
    seen, rows = set(), []
    for s in ("earned", "marketplaces"):
        d = load(domain, s)
        if not d:
            continue
        for i in d["items"]:
            m = i.get("meta", {})
            n = m.get("review_count")
            plat = m.get("platform") or m.get("marketplace")
            try:
                r = float(m.get("rating"))
            except (TypeError, ValueError):
                continue
            key = re.sub(r"\s*\(.*\)", "", plat or "").lower()
            if plat and key not in seen and 0 < r <= 5 and n != 0:
                seen.add(key)
                rows.append((plat, r, f"{n} reviews" if n else None))
    rows.sort(key=lambda r: -r[1])
    return C.hbar(rows, "Ratings by platform (out of 5)", domain_max=5, value_fmt=lambda v: f"{v:.1f}",
                  note="Official score and count as shown on each page; imported ratings flagged in the source list.") if rows else ""


def messaging_table(domain):
    d = load(domain, "wayback")
    if not d:
        return ""
    snaps = defaultdict(dict)
    for i in d["items"]:
        m = i["meta"]
        if m["field"] in ("title",) or (m["field"] == "heading" and "h1" not in snaps[(m["page"], i["date"])]):
            key = (m["page"], i["date"])
            q = (i["quote"] or "").replace("—", "-").replace("–", "-")  # verbatim titles may carry dashes
            if m["field"] == "title":
                snaps[key]["title"] = q
            else:
                snaps[key]["h1"] = q
            snaps[key]["url"] = i["url"]
    rows = sorted(((p, dt, v.get("title", ""), v.get("h1", ""), v["url"]) for (p, dt), v in snaps.items()), key=lambda r: (r[0], r[1]))
    if not rows:
        return ""
    tr = "".join(f'<tr><td>{C.esc(p)}</td><td><a href="{C.esc(u)}">{C.esc(dt)}</a></td><td>{C.esc(t)}</td><td>{C.esc(h)}</td></tr>'
                 for p, dt, t, h, u in rows)
    return C.figure("How the headline changed (Wayback snapshots)",
                    f'<div class="tw"><table class="grid small"><thead><tr><th>Page</th><th>Snapshot</th><th>Title</th><th>First heading</th></tr></thead><tbody>{tr}</tbody></table></div>',
                    note="Quarterly snapshots; dates link to the archived page.")


def datasets(a, cites):
    out = []
    for ds in a.get("datasets") or []:
        rows = ds.get("rows") or []
        if not rows:
            continue
        ref = cites.refs(ds.get("evidence"))
        if ds.get("kind") == "line":
            pts = [(r["label"], r["value"]) for r in rows if isinstance(r.get("value"), (int, float))]
            out.append(C.line([{"name": ds.get("title"), "points": pts}], ds.get("title"), ds.get("unit", ""), note=ds.get("note", "")))
        elif ds.get("kind") == "table" or not all(isinstance(r.get("value"), (int, float)) for r in rows):
            tr = "".join(f'<tr><td>{C.esc(r["label"])}</td><td>{C.esc(r.get("value"))}</td><td>{C.esc(r.get("note", ""))}</td></tr>' for r in rows)
            out.append(C.figure(ds.get("title"), f'<div class="tw"><table class="grid small"><tbody>{tr}</tbody></table></div>', note=ds.get("note", "")))
        else:
            out.append(C.hbar([(r["label"], r["value"], r.get("note") or None) for r in rows], ds.get("title"), ds.get("unit", ""),
                              note=ds.get("note", "")))
        if ref:
            out[-1] = out[-1].replace("</figcaption>", f"{ref}</figcaption>", 1)
    return out


def ai_answers_page(domain, company):
    """Standalone page with every raw AI answer (anchors match ai_visibility item urls)."""
    f = ROOT / "data" / domain / "_ai_raw.json"
    if not f.exists():
        return None
    raw = json.loads(f.read_text(encoding="utf-8"))
    by = defaultdict(list)
    for r in raw:
        by[r["provider"]].append(r)
    parts = []
    for p, rows in by.items():
        parts.append(f'<h2 id="{p}">{C.esc(rows[0]["model"])}</h2>')
        for r in sorted(rows, key=lambda r: r["idx"]):
            body = C.esc(r.get("text") or ("Error: " + r.get("error", "")))
            ws = "" if "no web search" not in json.dumps(r.get("usage", {})) else " (no web search)"
            cites = "".join(f"<li>{C.esc(c)}</li>" for c in dict.fromkeys(r.get("cites") or []))
            parts.append(f'<article id="{p}-{r["idx"]}"><h3>{C.esc(r["prompt"])}{ws}</h3><pre>{body}</pre>'
                         + (f"<details><summary>Cited sources</summary><ul>{cites}</ul></details>" if cites else "") + "</article>")
    return company, "\n".join(parts)



def _dated_counts(domain, source, types, days_back=90):
    """(last 90d, previous 90d) counts of dated items, homonyms excluded."""
    d = load(domain, source)
    if not d:
        return None
    today = date.today().toordinal()
    now = prev = 0
    for i in d["items"]:
        if i["type"] not in types or not i.get("date") or i.get("meta", {}).get("possible_homonym"):
            continue
        try:
            o = date.fromisoformat(i["date"][:10]).toordinal()
        except ValueError:
            continue
        if today - o <= days_back:
            now += 1
        elif today - o <= 2 * days_back:
            prev += 1
    return now, prev


def momentum(domain):
    """Rows: (signal, now, comparison, trend, source_url). Only signals with data."""
    rows = []
    for metric, label in (("organic_traffic", "Organic traffic / mo"), ("organic_keywords", "Ranking keywords"),
                          ("refdomains", "Referring domains")):
        ser = [s for s in _series(domain, metric) if s["name"] == domain]
        if ser and len(ser[0]["points"]) >= 4:
            pts = ser[0]["points"]
            (d0, v0), (d1, v1) = pts[-4], pts[-1]
            ch = (v1 - v0) / v0 * 100 if v0 else 0
            rows.append((label, C.fmt(v1), f"{ch:+.0f}% vs {d0[:7]}", "up" if ch > 5 else ("down" if ch < -5 else "flat"), ser[0]["url"]))
    for source, types, label in (("community", ("mention",), "Community mentions"), ("news", ("mention",), "News mentions"),
                                 ("releases", ("change",), "Product releases")):
        c = _dated_counts(domain, source, types)
        if c and (c[0] or c[1]):
            n, p = c
            rows.append((label, f"{n} in 90 days", f"{p} in the 90 days before", "up" if n > p else ("down" if n < p else "flat"), ""))
    soc = load(domain, "social")
    if soc:
        vids = [i for i in soc["items"] if i["type"] == "post" and i.get("meta", {}).get("platform") == "youtube" and i.get("date")]
        if vids:
            t = date.today().toordinal()
            n = sum(1 for v in vids if t - date.fromisoformat(v["date"]).toordinal() <= 90)
            p = sum(1 for v in vids if 90 < t - date.fromisoformat(v["date"]).toordinal() <= 180)
            rows.append(("YouTube uploads", f"{n} in 90 days", f"{p} in the 90 days before", "up" if n > p else ("down" if n < p else "flat"), ""))
    ads = load(domain, "ad_libraries")
    for i in (ads or {}).get("items", []):
        m = i.get("meta", {})
        if m.get("last_30_days") is not None:
            rows.append((f"{m['platform'].title()} ads", f"{m['last_30_days']} in 30 days", f"about {m['total_ads']} all time", None, i["url"]))
    hr = load(domain, "hiring")
    if hr:
        jobs = [i for i in hr["items"] if i["type"] == "job" and "Open roles published only" not in i["text"]]
        mk = sum(1 for j in jobs if j.get("meta", {}).get("marketing"))
        rows.append(("Open roles seen", str(len(jobs)), f"{mk} in marketing or growth", None, ""))
    return rows


def momentum_table(domain):
    rows = momentum(domain)
    if not rows:
        return ""
    arrow = {"up": "\u2191", "down": "\u2193", "flat": "\u2192"}
    tr = "".join(f'<tr><th scope="row">{C.esc(s)}</th><td class="num">{C.esc(n)}</td>'
                 f'<td class="t-{t or "none"}">{arrow.get(t, "")} {C.esc(cmp)}</td>'
                 f'<td>{f"<a class=fig-src href={chr(34)}{C.esc(u)}{chr(34)}>source</a>" if u else ""}</td></tr>'
                 for s, n, cmp, t, u in rows)
    return C.figure("Momentum, last 90 days", f'<div class="tw"><table class="grid small mom">{tr}</table></div>',
                    note="Collector counts; samples, not full coverage. Ahrefs: last full month vs three months earlier.")



def seo_figs(domain):
    """Brand share, positions, clusters, competitors, keyword gap table from seo.json."""
    d = load(domain, "seo")
    if not d:
        return []
    figs, gap = [], {"they_win": [], "we_win": []}
    clusters, comp, positions, brand = [], None, None, None
    for i in d["items"]:
        m = i.get("meta", {})
        if m.get("domain") not in (None, domain):
            continue
        if "cluster" in m and m.get("traffic") is not None:
            clusters.append((m["cluster"], m["traffic"], f'{m.get("keywords", "")} kw'))
        if "top3" in m:
            positions = [("Top 3", m.get("top3")), ("4-10", m.get("top4_10")), ("11-20", m.get("top11_20")), ("21-50", m.get("top21_50"))]
        if any(k in m for k in ("branded_traffic_share", "brand_share", "branded_share")):
            brand = (i["text"], i["url"])
        for k in ("competitors", "organic_competitors"):
            if isinstance(m.get(k), list):
                comp = m[k]
        if "competitor" in i["text"].lower() and isinstance(m.get("list"), list):
            comp = m["list"]
        if i["type"] == "keyword" and m.get("direction") in gap:
            gap[m["direction"]].append(i)
    if clusters:
        figs.append(C.hbar(sorted(clusters, key=lambda r: -r[1]), "Non-brand organic traffic by topic cluster",
                           note="Ahrefs top non-branded keywords grouped by intent.", src=d["items"][0]["url"]))
    if positions and all(v is not None for _, v in positions):
        figs.append(C.hbar([(k, v, None) for k, v in positions], "Ranking keywords by position", note="Ahrefs, latest snapshot."))
    if comp:
        rows = []
        for c in comp[:8]:
            if isinstance(c, dict):
                rows.append((c.get("domain") or c.get("competitor_domain"), c.get("common_keywords") or c.get("keywords_common") or 0, None))
        rows = [r for r in rows if r[0]]
        if rows:
            figs.append(C.hbar(rows, "Organic competitors (common keywords)", note="Ahrefs organic competitors."))
    tables = []
    for key, title in (("they_win", f"Keywords {domain} wins and the comparator does not"), ("we_win", "Keywords the comparator wins")):
        rows = sorted(gap[key], key=lambda i: -(i["meta"].get("volume") or 0))[:10]
        if rows:
            tr = "".join(f'<tr><td><a href="{C.esc(i["url"])}">{C.esc(i["text"].split(" (")[0][:60])}</a></td><td class="num">{C.fmt(i["meta"].get("volume"))}</td>'
                         f'<td class="num">{C.esc(i["meta"].get("pos_domain") or "-")}</td><td class="num">{C.esc(i["meta"].get("pos_comparator") or "-")}</td></tr>'
                         for i in rows)
            tables.append(C.figure(title, f'<div class="tw"><table class="grid small"><thead><tr><th>Keyword</th><th>Volume</th>'
                                          f'<th>{C.esc(domain)}</th><th>Comparator</th></tr></thead><tbody>{tr}</tbody></table></div>',
                                   note="Positions from Ahrefs organic keywords; '-' = not in the top 100 pulled."))
    return figs + tables, brand


def blog_figs(domain):
    d = load(domain, "blog")
    if not d:
        return []
    figs = []
    posts = [i for i in d["items"] if i["type"] == "post"]
    for i in d["items"]:
        m = i.get("meta", {})
        if isinstance(m.get("by_month"), dict) and m["by_month"]:
            keys = sorted(m["by_month"])[-12:]
            basis = m.get("label") or m.get("basis") or "sitemap lastmod (published or updated)"
            figs.append(C.columns([(k, m["by_month"][k]) for k in keys], "Blog posts per month",
                                  note=f"Basis: {basis}.", src=i["url"]))
            break
    for key, title in (("cluster", "Recent posts by topic"), ("stage", "Recent posts by funnel stage")):
        cnt = Counter(p.get("meta", {}).get(key) for p in posts if p.get("meta", {}).get(key))
        if cnt:
            figs.append(C.hbar([(k, v, None) for k, v in cnt.most_common(8)], title, note=f"{len(posts)} most recent posts."))
    stats, pages = [], None
    for i in d["items"]:
        m = i.get("meta", {})
        if "median_words" in m:
            stats.append({"label": "Median length", "value": f'{m["median_words"]:,} words', "sub": f'{m.get("median_h2", "")} H2s'})
        if "cta_share_pct" in m:
            stats.append({"label": "Posts with a product CTA", "value": f'{m["cta_share_pct"]:.0f}%', "sub": f'{m.get("with_cta")} of {m.get("sample")}'})
        if "with_video" in m:
            stats.append({"label": "Posts with video", "value": f'{m.get("share_pct", 0):.0f}%', "sub": f'{m["with_video"]} of {m.get("sample")}'})
        if "distinct_named" in m:
            stats.append({"label": "Bylines", "value": str(m["distinct_named"]), "sub": f'across {m.get("sample")} posts'})
        if "blog_pages" in m:
            pages = (m["blog_pages"], m.get("blog_share_pct"), i["url"])
        if isinstance(m.get("by_month"), dict) and m.get("total_urls"):
            stats.insert(0, {"label": "Posts, last 12 months", "value": str(sum(m["by_month"].values())), "sub": f'{m["total_urls"]:,} blog URLs'})
    if stats:
        figs.insert(0, C.stats(stats[:5]))
    if pages and pages[0]:
        tr = "".join(f'<tr><td><a href="{C.esc(x["url"])}">{C.esc(x["url"].split("/blog/")[-1].strip("/")[:60] or x["url"])}</a></td>'
                     f'<td class="num">{C.fmt(x.get("traffic"))}</td><td>{C.esc(x.get("keyword", ""))}</td></tr>' for x in pages[0][:8])
        figs.append(C.figure(f"Blog pages among the top organic pages ({pages[1]}% of top-page traffic)",
                             f'<div class="tw"><table class="grid small"><thead><tr><th>Post</th><th>Traffic / mo</th><th>Top keyword</th></tr></thead>'
                             f'<tbody>{tr}</tbody></table></div>', note="Ahrefs top pages; locale copies listed separately."))
    ranked = sorted([p for p in posts if p.get("meta", {}).get("ahrefs_traffic")], key=lambda p: -p["meta"]["ahrefs_traffic"])[:8]
    if ranked:
        tr = "".join(f'<tr><td><a href="{C.esc(p["url"])}">{C.esc(p["text"].split(" | ")[0][:70])}</a></td><td class="num">{C.fmt(p["meta"]["ahrefs_traffic"])}</td>'
                     f'<td>{C.esc(p["meta"].get("cluster", ""))}</td></tr>' for p in ranked)
        figs.append(C.figure("Blog posts that bring organic traffic", f'<div class="tw"><table class="grid small"><thead><tr><th>Post</th>'
                                                                   f'<th>Traffic / mo</th><th>Topic</th></tr></thead><tbody>{tr}</tbody></table></div>',
                             note="Ahrefs estimated monthly organic traffic."))
    return figs


def affiliate_media_figs(domain):
    d = load(domain, "affiliate_media")
    if not d:
        return []
    figs = []
    pages = [i for i in d["items"] if i["type"] == "page" and i.get("meta", {}).get("query")]
    mix = Counter(p["meta"].get("publisher_type") for p in pages if p["meta"].get("publisher_type"))
    if mix:
        figs.append(C.hbar([(k, v, None) for k, v in mix.most_common()], "Who ranks on money searches (review, alternatives, pricing, best)",
                           note=f"Top-10 results across {len({p['meta']['query'] for p in pages})} queries, Ahrefs SERP overview."))
    aff = sum(1 for p in pages if p["meta"].get("affiliate_link") is True)
    for i in d["items"]:
        m = i.get("meta", {})
        if isinstance(m.get("brand_counts"), dict) and m["brand_counts"]:
            figs.append(C.hbar(sorted(((k, v, None) for k, v in m["brand_counts"].items()), key=lambda r: -r[1])[:10],
                               "Brands named in 'best' list pages", highlight=domain.split(".")[0], note="Count of top-10 pages naming each brand.", src=i["url"]))
            break
    if pages:
        rows = sorted(pages, key=lambda p: (p["meta"]["query"], p["meta"].get("position") or 99))[:30]
        tr = "".join(f'<tr><td>{C.esc(p["meta"]["query"])}</td><td class="num">{C.esc(p["meta"].get("position"))}</td>'
                     f'<td><a href="{C.esc(p["url"])}">{C.esc(p["text"][:60])}</a></td><td>{C.esc(p["meta"].get("publisher_type"))}</td>'
                     f'<td>{"yes" if p["meta"].get("affiliate_link") is True else ("no" if p["meta"].get("affiliate_link") is False else "?")}</td></tr>' for p in rows)
        figs.append(C.figure(f"Money-search results ({aff} with backlink-confirmed affiliate links)", f'<details class="dt" open><summary>Show results</summary><div class="tw"><table class="grid small"><thead><tr>'
                                    f'<th>Query</th><th>Pos</th><th>Page</th><th>Type</th><th>Affiliate</th></tr></thead><tbody>{tr}</tbody></table></div></details>'))
    return figs
