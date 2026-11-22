"""Compare mode: N finished company runs side by side.

  python compare.py a.com b.com [c.com] [--lint-only]

Deterministic part (from collector JSON): metrics table, organic traffic overlay, channel matrix, pillars.
Analytic part (optional, from prompts/compare.md): data/_compare/<slug>/compare_analysis.json with themes heat map,
white space, head to head, insights, reader block. Output: output/compare-<slug>/index.html.
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

import build as B
from design import brand as BR
import charts as CH
import report_charts as RC

ROOT = Path(__file__).resolve().parent
CHANNELS = [  # normalized channel buckets (regex on each analysis.channels[].channel)
    ("LinkedIn ads", r"linkedin"), ("Google search ads", r"google|search ads|paid search|ppc"), ("Meta ads", r"meta|facebook|instagram"),
    ("Organic search", r"organic|seo|template|content"), ("Direct / brand", r"direct|brand"), ("Webinars / events", r"webinar|event"),
    ("Marketplaces / reviews", r"marketplace|review|app store"), ("YouTube", r"youtube|video"), ("Email", r"^email|newsletter|mail"),
    ("AI assistants", r"\bai\b|llm|chatgpt"), ("Community / social", r"community|social|reddit|x\b|twitter"),
    ("Affiliates / partners", r"affiliate|partner"), ("PR / press", r"\bpr\b|press"),
]


def analysis(d):
    f = ROOT / "data" / d / "analysis.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def primary_series(d, metric):
    ser = [s for s in RC._series(d, metric) if s["name"] == d]
    return ser[0] if ser else None


def metrics_row(d):
    a = analysis(d)
    row = {"Company": a.get("company") or d}
    sw = RC.load(d, "similarweb")
    for i in (sw or {}).get("items", []):
        if "visits" in i.get("meta", {}):
            row["Monthly visits"] = CH.fmt(i["meta"]["visits"])
    s = primary_series(d, "organic_traffic")
    if s and len(s["points"]) >= 13:
        last, yago = s["points"][-1][1], s["points"][-13][1]
        row["Organic traffic"] = CH.fmt(last)
        row["Organic, 12 mo"] = f"{(last - yago) / yago * 100:+.0f}%" if yago else "n/a"
    k = primary_series(d, "organic_keywords")
    if k:
        row["Ranking keywords"] = CH.fmt(k["points"][-1][1])
    r = primary_series(d, "refdomains")
    if r:
        row["Referring domains"] = CH.fmt(r["points"][-1][1])
    ads = RC.load(d, "ad_libraries")
    tot = {}
    for i in (ads or {}).get("items", []):
        m = i.get("meta", {})
        if "total_ads" in m:
            tot[m["platform"]] = max(tot.get(m["platform"], 0), RC.ad_count(m["total_ads"]) or 0)
    for p in ("linkedin", "google", "meta"):
        if p in tot:
            row[f"{'LinkedIn' if p == 'linkedin' else p.title()} ads (library total)"] = CH.fmt(tot[p])
    ai = RC.load(d, "ai_visibility")
    rows = [i["meta"] for i in (ai or {}).get("items", []) if "hits" in i.get("meta", {})]
    if rows:
        h, o = sum(x["hits"] for x in rows), sum(x["of"] for x in rows)
        row["AI answers naming it"] = f"{h} of {o}"
    sm = RC.load(d, "sitemap")
    b = {i["meta"]["bucket"]: i["meta"]["count"] for i in (sm or {}).get("items", []) if "bucket" in i.get("meta", {}) and "count" in i["meta"]}
    if b:
        row["Site pages"] = CH.fmt(sum(b.values()))
        row["Template pages"] = CH.fmt(b.get("templates", 0))
    st = RC.load(d, "stack")
    px = [i["meta"]["tool"] for i in (st or {}).get("items", []) if i.get("meta", {}).get("category") == "ad pixel"
          and i["meta"]["tool"].lower() != "summary"]
    if st:
        row["Ad pixels"] = str(len(set(px)))
    gh = RC.load(d, "github")
    for i in (gh or {}).get("items", []):
        if "public_repos" in i.get("meta", {}):
            row["GitHub repos"] = str(i["meta"]["public_repos"])
    return row


def channel_matrix(domains):
    lv = {}
    order = ["heavy", "active", "light", "not observed"]
    for d in domains:
        for c in analysis(d).get("channels", []):
            hits = [name for name, rx in CHANNELS if re.search(rx, c.get("channel", ""), re.I)]
            for k, name in enumerate(hits):
                v = c.get("verdict")
                if k and v == "heavy":  # a combined channel ("Content: blog, webinars") is heavy only in its first bucket
                    v = "active"
                prev = lv.get((name, d))
                if not prev or (v in order and order.index(v) < order.index(prev)):
                    lv[(name, d)] = v
    rows = []
    for name, _ in CHANNELS:
        if any((name, d) in lv for d in domains):
            cells = "".join(f'<td><span class="pill v-{B.VERDICT.get(lv.get((name, d)), "none")}">{B.esc(lv.get((name, d)) or "no data")}</span></td>'
                            for d in domains)
            rows.append(f"<tr><th scope='row'>{B.esc(name)}</th>{cells}</tr>")
    head = "".join(f"<th>{B.esc(analysis(d).get('company') or d)}</th>" for d in domains)
    return f'<div class="tw"><table class="grid"><thead><tr><th>Channel</th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def heat(ca, domains, C):
    if not ca.get("themes"):
        return ""
    head = "".join(f"<th>{B.esc(analysis(d).get('company') or d)}</th>" for d in domains)
    rows = []
    for t in ca["themes"]:
        cells = ""
        for d in domains:
            v = int(t.get("scores", {}).get(d, 0) or 0)
            cells += f'<td><span class="heat h{v}" title="{v} of 3">{["absent", "mention", "strong", "headline"][v]}</span></td>'
        rows.append(f'<tr><th scope="row">{B.esc(t["theme"])}{C.refs(t.get("evidence"))}</th>{cells}</tr>')
    return (f'<section><h2>Who owns which message</h2><div class="tw"><table class="grid heat-t"><thead><tr><th>Theme</th>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div><p class="fig-note">0 absent, 1 mention, 2 strong, 3 headline.</p></section>')


def lint(ca, domains):
    known = set()
    for d in domains:
        for f in (ROOT / "data" / d).glob("*.json"):
            if not f.name.startswith("_") and f.name not in ("analysis.json", "changes.json"):
                known |= {i.get("url") for i in json.loads(f.read_text(encoding="utf-8")).get("items", [])}
    errs = [e.get("url") for e in B.walk_evidence(ca) if e.get("url") not in known]
    if "—" in json.dumps(ca, ensure_ascii=False):
        errs.append("em dash")
    return errs


def main(domains, lint_only=False):
    slug = "-vs-".join(d.split(".")[0] for d in domains)
    ca_f = ROOT / "data" / "_compare" / slug / "compare_analysis.json"
    ca = json.loads(ca_f.read_text(encoding="utf-8")) if ca_f.exists() else {}
    if ca:
        errs = lint(ca, domains)
        if errs:
            print(f"LINT FAILED ({len(errs)}): {errs[:10]}")
            sys.exit(1)
        print("compare lint ok")
    if lint_only:
        return
    C = B.Cites()
    names = [analysis(d).get("company") or d for d in domains]
    h = [f'''<header class="top">{BR.LOGO}<div class="t-main"><p class="kind">{BR.NAME} · comparison</p>
<h1>{" vs ".join(B.esc(n) for n in names)}</h1><p class="meta">Generated {date.today().isoformat()} · public data only · single-company reports:
{" · ".join(f'<a href="../{B.esc(d)}/">{B.esc(n)}</a>' for d, n in zip(domains, names))}</p></div></header>''']
    if ca.get("tldr"):
        h.append('<section class="tldr"><h2>In short</h2><ul>' + "".join(f"<li>{B.esc(t)}</li>" for t in ca["tldr"]) + "</ul></section>")
    rows = [metrics_row(d) for d in domains]
    keys = [k for k in rows[0] if k != "Company"] + [k for r in rows[1:] for k in r if k not in rows[0]]
    keys = list(dict.fromkeys(keys))
    tr = "".join(f"<tr><th scope='row'>{B.esc(k)}</th>" + "".join(f"<td>{B.esc(r.get(k, 'n/a'))}</td>" for r in rows) + "</tr>" for k in keys)
    h.append(f'<section><h2>Numbers side by side</h2><div class="tw"><table class="grid"><thead><tr><th>Metric</th>'
             + "".join(f"<th>{B.esc(r['Company'])}</th>" for r in rows) + f'</tr></thead><tbody>{tr}</tbody></table></div>'
             '<p class="fig-note">Ahrefs and SimilarWeb estimates on the primary domain; ad counts as listed by each library.</p></section>')
    ser = [s for s in (primary_series(d, "organic_traffic") for d in domains) if s]
    if ser:
        for s, n in zip(ser, names):
            s["name"] = n
        figs = [CH.line(ser[:3], "Organic search traffic, monthly", note="Ahrefs estimates, primary domains, last full month shown.")]
        kw = [s for s in (primary_series(d, "organic_keywords") for d in domains) if s]
        for s, d in zip(kw, domains):
            s["name"] = analysis(d).get("company") or d
        if kw:
            figs.append(CH.line(kw[:3], "Ranking keywords, monthly", width=420))
        rd = [s for s in (primary_series(d, "refdomains") for d in domains) if s]
        for s, d in zip(rd, domains):
            s["name"] = analysis(d).get("company") or d
        if rd:
            figs.append(CH.line(rd[:3], "Referring domains", width=420))
        h.append(f'<section><h2>Dynamics</h2>{figs[0]}{B.grid(figs[1:])}</section>')
    h.append(heat(ca, domains, C))
    h.append(f'<section><h2>Where each puts effort</h2>{channel_matrix(domains)}</section>')
    pil = "".join(f'<div><h3 class="lb-h">{B.esc(n)}</h3><ol class="plain">'
                  + "".join(f'<li class="cp-row"><span>{B.esc(p["name"])}</span>{B.meter(p["source_count"], p["sources_total"])}</li>' for p in analysis(d).get("pillars", []))
                  + "</ol></div>" for d, n in zip(domains, names))
    h.append(f'<section><h2>Message pillars</h2><div class="two-l">{pil}</div></section>')
    if ca.get("head_to_head"):
        head = "".join(f"<th>{B.esc(n)}</th>" for n in names)
        tr = "".join(f'<tr><th scope="row" class="h2h-d">{B.esc(x["dimension"])}{C.refs(x.get("evidence"))}'
                     + (f'<span class="small-n h2h-n">{B.esc(x["note"])}</span>' if x.get("note") else "") + '</th>'
                     + "".join(f'<td{" class=edge" if x.get("edge") == d else ""}>{B.esc(x.get("lines", {}).get(d, ""))}</td>' for d in domains)
                     + "</tr>" for x in ca["head_to_head"])
        h.append(f'<section><h2>Head to head</h2><div class="tw"><table class="grid"><thead><tr><th>Dimension</th>{head}</tr></thead>'
                 f'<tbody>{tr}</tbody></table></div><p class="fig-note">Highlighted cell = edge on that dimension.</p></section>')
    for key, title in (("white_space", "White space"), ("insights", "So what for a marketer")):
        if ca.get(key):
            li = "".join(f'<li><h3>{B.esc(x["title"])}</h3><p>{B.esc(x["body"])}{C.refs(x.get("evidence"))}</p></li>' for x in ca[key])
            h.append(f'<section class="sowhat"><h2>{title}</h2><ol class="insights">{li}</ol></section>')
    lb = ca.get("lens_block")
    if lb:
        li = "".join(f'<li><h3>{B.esc(x["title"])}</h3><p>{B.esc(x["body"])}</p><p class="action"><b>Action</b> {B.esc(x.get("action"))}</p></li>'
                     for x in lb.get("items", []))
        h.append(f'<section class="lens"><h2>{B.esc(lb.get("title"))}</h2><ol class="insights">{li}</ol></section>')
    refs = "".join(f'<li><a href="{B.esc(u)}">{B.esc(C.meta[u].get("text") or u)}</a></li>' for u in C.order)
    if refs:
        h.append(f'<section class="foot"><details class="srcs"><summary><h2>Sources ({len(C.order)})</h2></summary><ol class="refs">{refs}</ol></details></section>')
    css = B.CSS + CH.CSS + B.EXTRA_CSS + """
.grid tbody th.h2h-d{white-space:normal;width:26%;min-width:180px}.h2h-n{display:block;font-weight:400;margin-top:6px;line-height:1.45}
@media (max-width:720px){.grid tbody th.h2h-d{width:auto;min-width:0}.heat{min-width:0}}
.cp-row{display:flex;justify-content:space-between;gap:12px;align-items:center;padding-top:8px;border-top:1px solid var(--line)}
.heat{display:inline-block;min-width:78px;text-align:center;font-size:12px;font-weight:600;padding:3px 8px;border-radius:6px}
.h0{background:var(--none-bg);color:var(--none)}.h1{background:color-mix(in oklab,var(--s1) 18%,var(--bg));color:var(--ink)}
.h2{background:color-mix(in oklab,var(--s1) 45%,var(--bg));color:var(--ink)}.h3{background:var(--s1);color:#fff}
td.edge{background:var(--ok-bg)}"""
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{B.esc(" vs ".join(names))}: marketing OSINT</title><meta name="robots" content="noindex">
{BR.HEAD}
<style>{css}</style></head><body><main>{"".join(x for x in h if x)}</main><script>{CH.JS}</script></body></html>"""
    out = ROOT / "output" / f"compare-{slug}" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"wrote {out} ({len(page) // 1024} KB)")


if __name__ == "__main__":
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    main(args, "--lint-only" in sys.argv)
