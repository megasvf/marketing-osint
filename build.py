"""Render data/<domain>/analysis.json into output/<domain>/index.html, with a lint gate.

Lint (build fails on any error):
  - every evidence entry has a url that appears verbatim in a collector file
  - no em dashes in rendered copy
  - every pillar carries source_count / sources_total
  - tldr has 2-4 lines

Usage: python build.py example.com [--no-lint]
"""
import html
import json
import re
import sys
from pathlib import Path

import charts as CH
from design import brand as BR
import costs as COSTS
import reader as RD
import report_charts as RC

ROOT = Path(__file__).resolve().parent
SOURCE_LABELS = {
    "site": "Website", "pricing": "Pricing (both billing modes)", "wayback": "Wayback Machine", "ahrefs_paid": "Ahrefs paid search",
    "ad_libraries": "Ad libraries", "ahrefs_organic": "Ahrefs organic", "similarweb": "SimilarWeb",
    "social": "Social", "earned": "Reviews & press", "ai_perception": "AI perception", "hiring": "Hiring",
    "ahrefs_history": "Ahrefs history", "ai_visibility": "AI visibility", "stack": "Martech stack", "sitemap": "Sitemap",
    "community": "Community", "news": "News", "github": "GitHub", "marketplaces": "Marketplaces",
    "email_archive": "Email archive", "corporate": "Corporate", "subdomains": "Subdomains",
    "releases": "Releases",
    "seo": "SEO deep dive", "blog": "Blog", "affiliate_media": "Affiliates & media", "linkedin": "LinkedIn page",
}
VERDICT = {"confirmed": "ok", "mixed": "warn", "contradicted": "bad", "no data": "none",
           "heavy": "heavy", "active": "active", "light": "light", "not observed": "none"}  # effort = neutral ramp, not a verdict


def esc(s):
    return html.escape(str(s or ""), quote=True)


class Cites:
    """Numbered citations: same URL -> same number."""

    def __init__(self):
        self.order, self.meta = [], {}

    def ref(self, ev):
        url = ev.get("url")
        if not url:
            return ""
        if url not in self.meta:
            self.order.append(url)
            self.meta[url] = ev
        n = self.order.index(url) + 1
        return f'<a class="cite" href="{esc(url)}" title="{esc(ev.get("quote") or ev.get("text"))}">{n}</a>'

    def refs(self, evs):
        seen, out = set(), []
        for e in evs or []:
            if e.get("url") and e["url"] not in seen:
                seen.add(e["url"])
                out.append(self.ref(e))
        return "".join(out)


def collector_urls(domain):
    urls = set()
    for f in (ROOT / "data" / domain).glob("*.json"):
        if f.name.startswith("_") or f.name == "analysis.json":
            continue
        for i in json.loads(f.read_text(encoding="utf-8")).get("items", []):
            urls.add(i.get("url"))
    return urls


def walk_evidence(o):
    if isinstance(o, dict):
        if "evidence" in o:
            yield from o["evidence"] or []
        for v in o.values():
            yield from walk_evidence(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk_evidence(v)


def lint(a, domain):
    errs, known = [], collector_urls(domain)
    evs = list(walk_evidence(a))
    for e in evs:
        if not e.get("url"):
            errs.append(f"evidence without url: {e.get('text', '')[:60]}")
        elif e["url"] not in known:
            errs.append(f"url not in collector data: {e['url']}")
    blob = json.dumps(a, ensure_ascii=False)
    if "—" in blob:
        errs.append(f"em dash found x{blob.count(chr(0x2014))}")
    for p in a.get("pillars", []):
        if not p.get("source_count") or not p.get("sources_total"):
            errs.append(f"pillar without source count: {p.get('name')}")
    if not 2 <= len(a.get("tldr", [])) <= 4:
        errs.append("tldr must have 2-4 lines")
    return errs, len(evs)


def meter(n, total):
    total = max(int(total or 0), 1)
    lab = f"{n} of {total} sources back this"
    if total > 10:  # many sources: proportional bar instead of one cell per source
        bar = f'<span class="meter-bar" role="img" aria-label="{lab}"><i style="width:{100 * n / total:.0f}%"></i></span>'
    else:
        cells = "".join(f'<i class="{"on" if k < n else ""}"></i>' for k in range(total))
        bar = f'<span class="meter" role="img" aria-label="{lab}">{cells}</span>'
    return f'<span class="meter-w" title="{lab}">{bar}<span class="meter-n">{n}/{total} sources</span></span>'


def conf(c):
    return f'<span class="conf conf-{esc(c)}">{esc(c)} confidence</span>' if c else ""


def header(a, sources, mode):
    """Shared header: title, format switch, source coverage strip."""
    d = a["domain"]
    cov = "".join(
        f'<li class="st-{esc(s["status"])}" title="{esc(s.get("note", "").replace(chr(0x2014), ";"))}"><b></b>{esc(SOURCE_LABELS.get(s["source"], s["source"]))}</li>'
        for s in sources)
    rn = RD.name(a)
    tabs = "".join(f'<a href="{href}"' + (' aria-current="page"' if m == mode else "") + f'>{label}</a>'
                   for m, href, label in (("brief", "index.html", "Dossier"), ("full", "full.html", "Detailed")))
    return f"""<header class="top">
  {BR.LOGO}
  <div class="t-main"><p class="kind">{BR.NAME} · detailed report</p>
  <h1>{esc(a.get("company"))} <span class="dom">{esc(d)}</span></h1>
  <p class="meta">Generated {esc(a.get("generated"))} · public data only{f" · written for {esc(rn)}" if rn else ""}</p></div>
  <nav class="fmt" aria-label="Report format">{tabs}</nav>
</header>
<section class="coverage" aria-label="Source coverage"><ul>{cov}</ul>
<p class="legend"><span class="st-ok"><b></b>collected</span><span class="st-partial"><b></b>partial</span><span class="st-unavailable"><b></b>unavailable</span></p></section>"""


def first_sentence(text):
    """First sentence; ignores dots inside numbers and 'vs.'."""
    m = re.search(r"(?<!\bvs)\.\s+(?=[A-Z])", text or "")
    return text[:m.start() + 1] if m else (text or "")


def short_date(d):
    """'2025-10-07 to 2026-10-07' -> '2025-10 to 2026-10'; single dates unchanged."""
    parts = re.findall(r"\d{4}-\d{2}(?:-\d{2})?", d or "")
    return f"{parts[0][:7]} to {parts[-1][:7]}" if len(parts) > 1 else (d or "")




def since_block(domain):
    """'Since last run' list from monitor.py changes.json (skipped on baseline or no changes)."""
    f = ROOT / "data" / domain / "changes.json"
    if not f.exists():
        return ""
    c = json.loads(f.read_text(encoding="utf-8"))
    if c.get("baseline") or not c.get("items"):
        return ""
    li = "".join(f'<li><span class="pill v-none">{esc(x["area"])}</span> '
                 + (f'<a href="{esc(x["url"])}">{esc(x["text"])}</a>' if x.get("url") else esc(x["text"])) + "</li>"
                 for x in c["items"][:12])
    return f'<section class="since"><h2>Since last run <span class="conf">{esc(c["since"])} to {esc(c["until"])}</span></h2><ul class="plain">{li}</ul></section>'



def card_block(a, C):
    """Company card: 6 tiles, short lines, one citation row per tile."""
    cc = a.get("company_card") or {}
    if not cc:
        return ""

    def lines(x):
        return "".join(f'<li><span class="cl">{esc(l.get("label"))}</span> {esc(l.get("value"))}</li>' for l in (x or {}).get("lines", []))
    po, ms, ec = cc.get("positioning") or {}, cc.get("messages") or {}, cc.get("economics") or {}
    tiles = []
    if po:
        tiles.append(("Positioning", f'<p class="cq">{esc(po.get("tagline"))}</p><p>{esc(po.get("formula"))}</p>', po.get("evidence")))
    if cc.get("model"):
        tiles.append(("Business model", f'<ul>{lines(cc["model"])}</ul>', cc["model"].get("evidence")))
    if ec:
        rows = "".join(f'<li><span class="cl">{esc(r.get("label"))}</span> <b>{esc(r.get("value"))}</b>'
                       f'{f" <small>{esc(r.get(chr(110) + chr(111) + chr(116) + chr(101)))}</small>" if r.get("note") else ""}</li>'
                       for r in ec.get("rows", []))
        tiles.append(("Economics", f"<ul>{rows}</ul>", ec.get("evidence")))
    if cc.get("audience"):
        tiles.append(("Audience", f'<ul>{lines(cc["audience"])}</ul>', cc["audience"].get("evidence")))
    if ms:
        chips = lambda xs: "".join(f'<span class="chip">{esc(x)}</span>' for x in xs or [])
        tiles.append(("Messages", f'<p class="cq">{esc(ms.get("tagline"))}</p><div class="chips-i">{chips(ms.get("pillars"))}</div>'
                      f'<p class="cs"><span class="cl">Proof</span> {esc("; ".join(ms.get("proof") or []))}</p>'
                      f'<p class="cs"><span class="cl">Tone</span> {esc(", ".join(ms.get("tone") or []))}</p>'
                      f'<p class="cs"><span class="cl">CTAs</span> {esc(" / ".join(ms.get("ctas") or []))}</p>', ms.get("evidence")))
    if cc.get("gtm"):
        tiles.append(("Go-to-market", f'<ul>{lines(cc["gtm"])}</ul>', cc["gtm"].get("evidence")))
    t = "".join(f'<div class="ct"><h3>{esc(h)}{C.refs((ev or [])[:3])}</h3>{body}</div>' for h, body, ev in tiles)
    return f'<section class="card"><h2>Company card</h2><div class="cards">{t}</div></section>'


def swot_block(a, C, compact=False):
    s = a.get("swot") or {}
    if not any(s.get(k) for k in ("strengths", "weaknesses", "opportunities", "threats")):
        return ""
    q = []
    for k, title, cls in (("strengths", "Strengths", "sw-s"), ("weaknesses", "Weaknesses", "sw-w"),
                          ("opportunities", "Opportunities", "sw-o"), ("threats", "Threats", "sw-t")):
        items = s.get(k) or []
        li = "".join(f'<li>{esc(first_sentence(x["text"]) if compact else x["text"])}{C.refs((x.get("evidence") or [])[:1 if compact else 3])}</li>'
                     for x in items[: 3 if compact else 5])
        q.append(f'<div class="sw {cls}"><p class="tag">{title}</p><ul>{li}</ul></div>')
    return f'<section><h2>SWOT ({esc(a.get("company"))})</h2><div class="swot">{"".join(q)}</div></section>'


def battlecard_block(a, C, compact=False):
    bc = a.get("battlecard") or {}
    if not bc:
        return ""
    rn = RD.name(a) or "You"
    ob = "".join(f'<li><p class="obj">\u201c{esc(o["objection"])}\u201d</p><p>{esc(first_sentence(o["answer"]) if compact else o["answer"])}'
                 f'{C.refs((o.get("evidence") or [])[:1])}</p>'
                 + "</li>"
                 for o in (bc.get("objections") or [])[: 3 if compact else 6])
    lm = "".join(f'<li>{esc(x["text"])}{C.refs((x.get("evidence") or [])[:1])}</li>' for x in (bc.get("landmines") or [])[: 3 if compact else 6])
    pc = "".join(f'<tr><th scope="row">{esc(r.get("item"))}</th><td>{esc(r.get("them"))}</td><td>{esc(r.get("reader"))}</td>'
                 f'<td class="small-n">{esc(r.get("note"))}</td></tr>' for r in bc.get("price_compare") or [])
    pct = (f'<h3 class="lb-h">Price check</h3><div class="tw"><table class="grid small"><thead><tr><th>Item</th><th>{esc(a.get("company"))}</th>'
           f'<th>{esc(rn)}</th><th>Note</th></tr></thead><tbody>{pc}</tbody></table></div>') if pc else ""
    return (f'<section class="battle"><h2>Battlecard: {esc(rn)} vs {esc(a.get("company"))}</h2><div class="two-l">'
            f'<div><h3 class="lb-h">Objections and answers</h3><ol class="plain obj-l">{ob}</ol></div>'
            f'<div><h3 class="lb-h">Landmines to ask about</h3><ul class="plain">{lm}</ul></div></div>{pct}</section>')


def moves_block(a, C, days=90):
    """Dated changes within the last `days` (synthesis changes with an end date in range)."""
    from datetime import date as _d
    today = _d.today().toordinal()
    out = []
    for c in a.get("changes", []):
        ds = re.findall(r"\d{4}-\d{2}(?:-\d{2})?", c.get("date") or "")
        if not ds:
            continue
        last = ds[-1] + ("-15" if len(ds[-1]) == 7 else "")
        try:
            if today - _d.fromisoformat(last).toordinal() <= days:
                out.append((last, c))
        except ValueError:
            continue
    if not out:
        return ""
    li = "".join(f'<li><time>{esc(short_date(c.get("date")))}</time><span>{esc(first_sentence(c.get("after")))}{C.refs((c.get("evidence") or [])[:1])}</span></li>'
                 for _, c in sorted(out, key=lambda x: x[0], reverse=True))
    return f'<div><h3 class="lb-h">Moves in the last {days} days</h3><ul class="b-chg">{li}</ul></div>'



def cost_block(domain, compact=False):
    """Footer: paid APIs / tools used for this run (from data/<domain>/_run_cost.json)."""
    rows = COSTS.summary(domain)
    if not rows:
        return ""
    free = ("Free sources: site pages, Wayback Machine, public ad libraries (Google, Meta, LinkedIn, Microsoft, TikTok), "
            "G2 and Trustpilot pages, GitHub API, Google News RSS, Hacker News, crt.sh. Agent work runs on the Claude subscription (not metered here).")
    if compact:
        parts = [f"{esc(t)} {COSTS_fmt(a)} {esc(u)}" + (" (cache)" if b == "cache" else "") for t, b, a, u, _ in rows]
        return (f'<section class="costs"><p><b>Paid tools used:</b> {"; ".join(parts)}. '
                f'<a href="full.html#costs">Details</a></p></section>')
    tr = "".join(f'<tr><th scope="row">{esc(t)}</th><td class="num">{COSTS_fmt(a)} {esc(u)}</td><td>{esc(b)}</td>'
                 f'<td class="small-n">{esc("; ".join(n))}</td></tr>' for t, b, a, u, n in rows)
    return (f'<section class="costs" id="costs"><h2>Paid tools used in this run</h2><div class="tw"><table class="grid small">'
            f'<thead><tr><th>Tool</th><th>Usage</th><th>Billing</th><th>Notes</th></tr></thead><tbody>{tr}</tbody></table></div>'
            f'<p class="fig-note">{esc(free)}</p></section>')


def COSTS_fmt(a):
    return f"{a:,}" if isinstance(a, int) else f"{a:,.2f}"



def briefs_block(a, C, compact=False):
    """Per-unit briefs: 2-3 insights + actions for each marketing unit."""
    br = a.get("department_briefs") or []
    if not br:
        return ""
    tiles = []
    for u in br:
        ins = u.get("insights") or []
        li = "".join(f'<li>{esc(first_sentence(x["text"]) if compact else x["text"])}{C.refs((x.get("evidence") or [])[:1])}'
                     f'<p class="act"><b>Do:</b> {esc(x.get("action"))}</p></li>' for x in ins[: 2 if compact else 3])
        tiles.append(f'<div class="ct"><h3>{esc(u.get("unit"))}</h3><ul class="br-l">{li}</ul></div>')
    return f'<section class="card"><h2>For each marketing unit</h2><div class="cards">{"".join(tiles)}</div></section>'


def text_points(title, block, C, keys=("takeaways", "points", "copy", "avoid")):
    if not block:
        return ""
    parts = [f'<p class="lead-p">{esc(block.get("text"))}</p>'] if block.get("text") else []
    for k in keys:
        if block.get(k):
            label = {"copy": "Worth copying", "avoid": "Avoid"}.get(k, "")
            parts.append(list_block(label, block[k], C))
    return "".join(parts)


def key_stats(a, C):
    """Headline figures: synthesis key_numbers (cited) or deterministic fallbacks."""
    d, brand = a["domain"], a.get("company", "")
    items = []
    for k in a.get("key_numbers") or []:
        ev = (k.get("evidence") or [{}])[0]
        if ev.get("url"):
            C.ref(ev)
        items.append({"label": k.get("label"), "value": k.get("value"), "sub": k.get("sub"), "trend": k.get("trend"),
                      "href": ev.get("url")})
    if not items:
        items = [x for x in (RC.sw_stats(d), RC.ai_stat(d, brand)) if x]
    return CH.stats(items[:6]) if items else ""


def grid(figs):
    figs = [f for f in figs if f]
    return f'<div class="figs">{"".join(figs)}</div>' if figs else ""


def list_block(title, rows, C, key="text", label=None):
    rows = rows or []
    if not rows:
        return ""
    li = "".join(f'<li>{"<b>" + esc(r.get(label)) + "</b> " if label and r.get(label) else ""}{esc(r.get(key))}{C.refs(r.get("evidence"))}</li>'
                 for r in rows)
    return f'<div><h3 class="lb-h">{esc(title)}</h3><ul class="plain">{li}</ul></div>'


def render_brief(a, sources):
    """One-screen format: answer first, one citation per line, no tables."""
    C = Cites()
    h = [header(a, sources, "brief")]
    h.append('<section class="tldr"><h2>In short</h2><ul>' + "".join(f"<li>{esc(t)}</li>" for t in a["tldr"]) + "</ul></section>")
    d = a["domain"]
    h.append(since_block(d))
    h.append(card_block(a, C))
    h.append(f'<section class="b-key">{key_stats(a, C)}{RC.headline_traffic(d)}</section>')
    mt, mv = RC.momentum_table(d), moves_block(a, C)
    if mt or mv:
        h.append(f'<section><h2>Momentum</h2><div class="b-grid b-even">{mt}{mv}</div></section>')
    pr = a["promise"]
    pil = "".join(f'<li><span>{esc(p["name"])}</span><span>{meter(p["source_count"], p["sources_total"])}</span></li>'
                  for p in a.get("pillars", []))
    order = ["heavy", "active", "light", "not observed"]
    chans = sorted(a.get("channels", []), key=lambda c: order.index(c["verdict"]) if c.get("verdict") in order else 9)
    ch = "".join(f'<li><span class="pill v-{VERDICT.get(c.get("verdict"), "none")}">{esc(c.get("verdict"))}</span> {esc(c["channel"])}</li>'
                 for c in chans)
    h.append(f"""<section class="b-grid"><div><div class="s-head"><h2>Promise</h2>{conf(pr.get("confidence"))}</div>
<p class="promise-s">{esc(pr["text"])}{C.refs(pr.get("evidence", [])[:1])}</p><ul class="b-pillars">{pil}</ul></div>
<div><h2>Channels</h2><ul class="b-chan">{ch}</ul></div></section>""")
    ai_f, paid_f = RC.ai(d, a.get("company", "")), RC.paid(d)
    h.append(f'<section><h2>Visibility at a glance</h2>{grid([ai_f[0] if ai_f else "", paid_f[0] if paid_f else ""])}</section>')
    sv = "".join(f'<li><span class="pill v-{VERDICT.get(r.get("verdict"), "none")}">{esc(r.get("verdict"))}</span><span>{esc(r["claim"])}</span></li>'
                 for r in a.get("say_vs_heard", []))
    cg = "".join(f'<li><time>{esc(short_date(c.get("date")))}</time><span>{esc(c.get("after"))}{C.refs(c.get("evidence", [])[:1])}</span></li>'
                 for c in a.get("changes", [])[:4])
    h.append(f"""<section class="b-grid b-even"><div><h2>Claim check</h2><ul class="b-sv">{sv}</ul></div>
<div><h2>What changed</h2><ul class="b-chg">{cg}</ul></div></section>""")
    h.append(swot_block(a, C, compact=True))
    h.append(battlecard_block(a, C, compact=True))
    h.append(briefs_block(a, C, compact=True))
    sw = a.get("so_what", {})
    ins = "".join(f'<li><b>{esc(i["title"])}.</b> {esc(first_sentence(i["body"]))}{C.refs(i.get("evidence", [])[:1])}</li>'
                  for i in sw.get("insights", []))
    st, av = sw.get("steal") or {}, sw.get("avoid") or {}
    h.append(f"""<section class="sowhat"><h2>So what</h2><ol class="insights b-ins">{ins}</ol>
<div class="sa"><div class="steal"><p class="tag">Steal</p><p><b>{esc(st.get("title"))}.</b> {esc(first_sentence(st.get("body")))}</p></div>
<div class="avoid"><p class="tag">Avoid</p><p><b>{esc(av.get("title"))}.</b> {esc(first_sentence(av.get("body")))}</p></div></div></section>""")
    lb = a.get("lens_block")
    if lb:
        li = "".join(f'<li><b>{esc(x["title"])}.</b> {esc(first_sentence(x.get("action")))}</li>' for x in lb.get("items", []))
        h.append(f'<section class="lens"><h2>{esc(lb.get("title"))}</h2><ol class="insights b-ins">{li}</ol></section>')
    gaps = ", ".join(esc(SOURCE_LABELS.get(g["source"], g["source"])) for g in a.get("gaps", []))
    n_ev = len(list(walk_evidence(a)))
    h.append(cost_block(d, compact=True))
    h.append(f"""<section class="b-foot"><p><b>Gaps:</b> {gaps or "none"}.</p>
<p><a href="full.html">Detailed report with all {n_ev} evidence links</a></p></section>""")
    return "\n".join(h), len(C.order)


def render(a, sources):
    C = Cites()
    h = [header(a, sources, "full")]
    d, brand = a["domain"], a.get("company", "")
    # tldr + headline figures
    h.append('<section class="tldr"><h2>In short</h2><ul>' + "".join(f"<li>{esc(t)}</li>" for t in a["tldr"]) + "</ul></section>")
    h.append(since_block(d))
    h.append(f'<section class="b-key">{key_stats(a, C)}</section>')
    h.append(card_block(a, C))
    # promise + pillars
    pr = a["promise"]
    rows = "".join(f'''<li><div class="p-head"><h3>{esc(p["name"])}</h3>{meter(p["source_count"], p["sources_total"])}</div>
<p>{esc(p.get("desc"))}{C.refs(p.get("evidence"))}</p></li>''' for p in a.get("pillars", []))
    h.append(f'''<section><div class="s-head"><h2>What they promise</h2>{conf(pr.get("confidence"))}</div>
<p class="promise">{esc(pr["text"])}{C.refs(pr.get("evidence"))}</p>
<ol class="pillars">{rows}</ol></section>''')
    # dynamics + traffic (collector numbers)
    dyn = RC.dynamics(d)
    if dyn:
        h.append(f'<section><h2>Dynamics</h2>{dyn[0]}{grid(dyn[1:])}{RC.momentum_table(d)}</section>')
    tr = RC.traffic(d)
    if tr:
        h.append(f'<section><h2>Traffic and audience</h2>{grid(tr)}</section>')
    # audience & offer
    au = a.get("audience", {})
    segs = "".join(f'<li><b>{esc(s["name"])}</b> {esc(s.get("signal"))}{C.refs(s.get("evidence"))}</li>' for s in au.get("segments", []))
    off = au.get("offer") or {}
    h.append(f'''<section class="two"><div><div class="s-head"><h2>Who they target</h2>{conf(au.get("confidence"))}</div><ul class="plain">{segs}</ul></div>
<div><h2>Entry offer</h2><p>{esc(off.get("text"))}{C.refs(off.get("evidence"))}</p></div></section>''')
    # channels
    ch = "".join(f'''<tr><th scope="row">{esc(c["channel"])}</th><td><span class="pill v-{VERDICT.get(c.get("verdict"), "none")}">{esc(c.get("verdict"))}</span></td>
<td>{esc(c.get("signal"))}{C.refs(c.get("evidence"))}</td></tr>''' for c in a.get("channels", []))
    h.append(f'<section><h2>Where they put effort</h2><table class="grid"><thead><tr><th>Channel</th><th>Level</th><th>Signal</th></tr></thead><tbody>{ch}</tbody></table>{grid(RC.paid(d))}</section>')
    # AI visibility
    av = a.get("ai_visibility") or {}
    ai_f = RC.ai(d, brand)
    if ai_f or av:
        txt = f'<p class="lead-p">{esc(av.get("text"))}{C.refs(av.get("evidence"))} {conf(av.get("confidence"))}</p>' if av.get("text") else ""
        h.append(f'<section><h2>AI visibility</h2>{txt}{grid(ai_f)}<p class="fig-note"><a href="ai_answers.html">Read every raw AI answer</a></p></section>')
    # content, community, stack
    cf = RC.content(d)
    ce = list_block("Content engine", a.get("content_engine"), C, label="area")
    if cf or ce:
        h.append(f'<section><h2>Content and community</h2>{grid(cf)}{ce}</section>')
    sf = RC.seo_figs(d)
    seo_figs = sf[0] if sf else []
    if seo_figs or a.get("seo"):
        h.append(f'<section><h2>SEO</h2>{text_points("SEO", a.get("seo"), C)}{grid(seo_figs)}</section>')
    bf = RC.blog_figs(d)
    if bf or a.get("content_strategy"):
        bstats = bf.pop(0) if bf and 'class="stats"' in bf[0] else ""
        h.append(f'<section><h2>Blog and content strategy</h2>{text_points("Content", a.get("content_strategy"), C)}{bstats}{grid(bf)}</section>')
    af = RC.affiliate_media_figs(d)
    if af or a.get("affiliate_media"):
        h.append(f'<section><h2>Affiliates, reviewers and media</h2>{text_points("Affiliates", a.get("affiliate_media"), C)}{grid(af)}</section>')
    # go-to-market: motion, proof, ecosystem, stack
    mo = a.get("motion") or {}
    gtm = []
    if mo.get("text"):
        gtm.append(f'<div><h3 class="lb-h">Motion: {esc(mo.get("type"))}</h3><p>{esc(mo["text"])}</p>'
                   + list_block("", mo.get("signals"), C).replace('<h3 class="lb-h"></h3>', "") + "</div>")
    gtm.append(list_block("Proof they use", a.get("proof"), C, label="type"))
    gtm.append(list_block("Ecosystem", a.get("ecosystem"), C, label="area"))
    stk = RC.stack(d)
    if any(gtm) or stk:
        h.append(f'<section><h2>Go-to-market</h2><div class="two-l">{"".join(g for g in gtm if g)}</div>{stk}</section>')
    # reviews
    rt = RC.ratings(d)
    if rt:
        h.append(f'<section><h2>Reviews</h2>{rt}</section>')
    # say vs heard
    sv = "".join(f'''<tr><td>{esc(r["claim"])}</td><td>{esc(r["heard"])}{C.refs(r.get("evidence"))}</td>
<td><span class="pill v-{VERDICT.get(r.get("verdict"), "none")}">{esc(r.get("verdict"))}</span></td></tr>''' for r in a.get("say_vs_heard", []))
    h.append(f'<section><h2>What they say vs what customers say</h2><table class="grid"><thead><tr><th>They say</th><th>Others say</th><th>Verdict</th></tr></thead><tbody>{sv}</tbody></table></section>')
    # changes
    cg = "".join(f'''<li><time>{esc(c.get("date"))}</time><div><p class="before">{esc(c.get("before"))}</p>
<p class="after">{esc(c.get("after"))}{C.refs(c.get("evidence"))}</p></div></li>''' for c in a.get("changes", []))
    tl = CH.timeline([{"date": (re.findall(r"\d{4}-\d{2}-\d{2}", c.get("date") or "") or [""])[0], "label": first_sentence(c.get("after"))}
                      for c in a.get("changes", [])], "Timeline")
    h.append(f'<section><h2>What changed</h2>{tl}<ol class="timeline">{cg}</ol>{RC.messaging_table(d)}</section>')
    # business signals + extra datasets
    biz = list_block("Business signals", a.get("business"), C)
    ds = RC.datasets(a, C)
    if biz or ds:
        h.append(f'<section><h2>Business signals</h2>{biz}{grid(ds)}</section>')
    h.append(swot_block(a, C))
    h.append(briefs_block(a, C))
    # so what
    sw = a.get("so_what", {})
    ins = "".join(f'<li><h3>{esc(i["title"])}</h3><p>{esc(i["body"])}{C.refs(i.get("evidence"))}</p></li>' for i in sw.get("insights", []))
    st, av = sw.get("steal") or {}, sw.get("avoid") or {}
    h.append(f'''<section class="sowhat"><h2>So what for a marketer</h2><ol class="insights">{ins}</ol>
<div class="sa"><div class="steal"><p class="tag">Steal</p><h3>{esc(st.get("title"))}</h3><p>{esc(st.get("body"))}</p></div>
<div class="avoid"><p class="tag">Avoid</p><h3>{esc(av.get("title"))}</h3><p>{esc(av.get("body"))}</p></div></div></section>''')
    # reader block
    lb = a.get("lens_block")
    if lb:
        li = "".join(f'''<li><h3>{esc(x["title"])}</h3><p>{esc(x["body"])}</p><p class="action"><b>Action</b> {esc(x.get("action"))}</p></li>''' for x in lb.get("items", []))
        aa = "".join(f'''<tr><td>{esc(x.get("their_weakness"))}{C.refs(x.get("evidence"))}</td><td>{esc(x.get("reader_strength"))}</td><td>{esc(x.get("angle"))}</td></tr>'''
                     for x in lb.get("attack_angles") or [])
        aa_t = (f'<h3 class="lb-h">Attack angles</h3><div class="tw"><table class="grid"><thead><tr><th>Their weak spot</th><th>{esc(RD.name(a) or "Your")} strength</th>'
                f'<th>Angle</th></tr></thead><tbody>{aa}</tbody></table></div>') if aa else ""
        h.append(f'<section class="lens"><h2>{esc(lb.get("title"))}</h2><ol class="insights">{li}</ol>{aa_t}</section>')
        h.append(battlecard_block(a, C))
    # gaps + sources
    gaps = "".join(f'<li><b>{esc(SOURCE_LABELS.get(g["source"], g["source"]))}</b> {esc(g["reason"])}</li>' for g in a.get("gaps", []))
    refs = "".join(f'<li><a href="{esc(u)}">{esc(C.meta[u].get("text") or u)}</a> <span class="u">{esc(u)}</span></li>' for u in C.order)
    h.append(f'''<section class="foot"><div><h2>Gaps</h2><ul class="plain">{gaps or "<li>None</li>"}</ul></div>
<details class="srcs"><summary><h2>Sources ({len(C.order)})</h2></summary><ol class="refs">{refs}</ol></details></section>''')
    h.append(cost_block(d))
    return "\n".join(h), len(C.order)


EXTRA_CSS = """
.br-l{list-style:none;margin:0;padding:0;display:grid;gap:8px;font-size:13.5px}.br-l .act{font-size:12.5px;color:var(--ink-2);margin-top:2px}.br-l .act b{color:var(--ok)}
.costs{font-size:13px}.costs p{color:var(--ink-2)}.costs td.num{white-space:nowrap;font-variant-numeric:tabular-nums;font-weight:600}
.card{border-top:0}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--line);border-radius:10px;overflow:hidden}
.ct{background:var(--bg);padding:14px 16px;min-width:0}.ct h3{font-size:13px;color:var(--ink-2);font-weight:600;margin-bottom:8px}
.ct ul{list-style:none;margin:0;padding:0;display:grid;gap:5px;font-size:13.5px}.ct p{font-size:13.5px;margin-bottom:6px}
.cl{color:var(--ink-2);font-size:12px;margin-right:4px}.cq{font-weight:600;font-size:14px}.cs{font-size:12.5px}
.chips-i{display:flex;flex-wrap:wrap;gap:4px;margin:6px 0}.chips-i .chip{font-size:11.5px}
.swot{display:grid;grid-template-columns:1fr 1fr;gap:12px}.sw{border-radius:10px;padding:12px 16px;background:var(--surf)}
.sw ul{margin:0;padding-left:18px;display:grid;gap:5px;font-size:13.5px}.sw-s .tag,.sw-o .tag{color:var(--ok)}.sw-w .tag,.sw-t .tag{color:var(--bad)}
.battle .obj{font-weight:600;margin-bottom:2px}.obj-l{gap:12px}.small-n{font-size:12px;color:var(--ink-2)}
.mom td.num{font-variant-numeric:tabular-nums;font-weight:600;white-space:nowrap}
@media (max-width:860px){.cards{grid-template-columns:1fr 1fr}}@media (max-width:560px){.cards,.swot{grid-template-columns:1fr}}
.b-key{border-top:0;padding-top:8px}.since .plain{gap:6px;font-size:14px}.lead-p{margin-bottom:14px}.lb-h{font-size:14px;margin:14px 0 8px}
.two-l{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:4px 32px;margin-bottom:12px}
.tw{overflow-x:auto}
.ai-page article{border-top:1px solid var(--line);padding:16px 0}.ai-page pre{white-space:pre-wrap;font:13px/1.5 var(--font-sans);margin:8px 0}
"""


CSS = BR.TOKENS + """
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 var(--font-sans);font-feature-settings:"cv11","ss01"}
main{max-width:1040px;margin:0 auto;padding:32px 24px 64px}
h1,h2,h3{text-wrap:balance;margin:0}h1{font:700 32px/1.15 var(--font-serif);letter-spacing:-.01em}
h2{font:700 21px/1.25 var(--font-serif);margin-bottom:12px}h3{font-size:15px;font-weight:600}
p{margin:0;text-wrap:pretty;max-width:75ch}
section{padding:24px 0;border-top:1px solid var(--line)}
.top{display:flex;gap:16px;align-items:flex-start;padding-bottom:20px}
.logo{display:block;flex:none;margin-top:4px}.hl{color:inherit;background:linear-gradient(transparent 52%,var(--mark) 52%);-webkit-box-decoration-break:clone;box-decoration-break:clone}
.kind{font-size:13px;color:var(--ink-2)}.dom{font-weight:400;color:var(--ink-2);font-size:20px}.meta{font-size:13px;color:var(--ink-2);margin-top:4px}
.coverage ul{display:flex;flex-wrap:wrap;gap:6px 18px;list-style:none;margin:0;padding:0;font-size:13px}
.coverage li,.legend span{display:inline-flex;align-items:center;gap:6px}
.coverage b,.legend b{width:9px;height:9px;border-radius:50%;display:inline-block;border:1.5px solid var(--ink-2)}
.st-ok b{background:var(--ok);border-color:var(--ok)}.st-partial b{background:linear-gradient(90deg,var(--warn) 50%,transparent 50%);border-color:var(--warn)}
.st-unavailable{color:var(--ink-2)}.st-unavailable b{border-style:dashed}
.legend{display:flex;gap:16px;font-size:12px;color:var(--ink-2);margin-top:10px}
.tldr{background:var(--surf);border:0;border-radius:10px;padding:20px 24px;margin:8px 0 8px}
.tldr ul{margin:0;padding-left:18px;display:grid;gap:6px;font-size:16px}
.s-head{display:flex;gap:12px;align-items:baseline;flex-wrap:wrap}.s-head h2{margin-bottom:12px}
.conf{font-size:12px;color:var(--ink-2)}.conf-low{color:var(--warn)}
.promise{font-size:18px;line-height:1.45;font-weight:500;margin-bottom:16px}
.pillars{list-style:none;margin:0;padding:0;display:grid;gap:0}
.pillars li{padding:12px 0;border-top:1px solid var(--line)}.pillars li:first-child{border-top:0}
.p-head{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:4px}
.meter{display:inline-flex;gap:3px}.meter i{width:10px;height:10px;border-radius:2px;background:var(--line)}.meter i.on{background:var(--ink)}
.meter-bar{display:inline-block;width:96px;height:8px;border-radius:4px;background:var(--line);overflow:hidden;vertical-align:middle}.meter-bar i{display:block;height:100%;background:var(--ink)}
.meter-w{display:inline-flex;align-items:center;flex:none;white-space:nowrap}.meter-n{font-size:12px;color:var(--ink-2);margin-left:8px;font-variant-numeric:tabular-nums;min-width:8.5em}
.two{display:grid;grid-template-columns:3fr 2fr;gap:32px}
.plain{list-style:none;margin:0;padding:0;display:grid;gap:8px}.plain b{font-weight:600;margin-right:4px}
table.grid{width:100%;border-collapse:collapse;font-size:14px}
.grid th,.grid td{text-align:left;vertical-align:top;padding:10px 12px 10px 0;border-top:1px solid var(--line)}
.grid thead th{font-size:12px;font-weight:600;color:var(--ink-2);border-top:0;padding-top:0}
.grid tbody th{font-weight:600;white-space:nowrap}
.pill{display:inline-block;font-size:12px;font-weight:600;padding:2px 8px;border-radius:999px;white-space:nowrap}
.v-ok{color:var(--ok);background:var(--ok-bg)}.v-warn{color:var(--warn);background:var(--warn-bg)}
.v-bad{color:var(--bad);background:var(--bad-bg)}.v-none{color:var(--none);background:var(--none-bg)}
.v-heavy{color:var(--bg);background:var(--ink)}.v-active{color:var(--ink);background:var(--surf);box-shadow:inset 0 0 0 1px var(--ink-2)}.v-light{color:var(--ink-2);background:transparent;box-shadow:inset 0 0 0 1px var(--line)}
.timeline{list-style:none;margin:0;padding:0;display:grid;gap:14px}
.timeline li{display:grid;grid-template-columns:136px 1fr;gap:16px}
.timeline time{font-size:13px;color:var(--ink-2);font-variant-numeric:tabular-nums;padding-top:1px;white-space:nowrap}
.before{color:var(--ink-2);text-decoration:line-through;text-decoration-color:var(--line);text-decoration-thickness:1px}
.after{font-weight:500}
.insights{margin:0;padding-left:22px;display:grid;gap:14px}.insights li::marker{font-weight:700}
.insights h3{margin-bottom:2px}
.sa{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:20px}
.steal,.avoid{border-radius:10px;padding:16px 18px;background:var(--surf)}
.tag{font-size:12px;font-weight:700;margin-bottom:4px}.steal .tag{color:var(--ok)}.avoid .tag{color:var(--bad)}
.lens{background:var(--surf);border-radius:10px;padding:20px 24px;border:0;margin-top:8px}
.action{margin-top:4px}.action b{color:var(--ok)}
.foot{display:grid;grid-template-columns:1fr 2fr;gap:32px;font-size:13px}
.srcs summary{cursor:pointer;list-style:none}.srcs summary::-webkit-details-marker{display:none}
.srcs summary h2{display:inline-flex;gap:8px;align-items:center}.srcs summary h2::after{content:"Show";font-size:12px;font-weight:500;color:var(--ink-2);border:1px solid var(--line);border-radius:999px;padding:1px 8px}
.srcs[open] summary h2::after{content:"Hide"}
.refs{margin:0;padding-left:22px;display:grid;gap:6px}.refs .u{display:block;color:var(--ink-2);font-size:11px;word-break:break-all}
a{color:inherit;text-underline-offset:2px}
.cite{display:inline-block;font:600 10px/1 var(--font-mono);line-height:1;vertical-align:super;margin-left:2px;padding:2px 4px;
border-radius:4px;background:var(--surf);color:var(--ink-2);text-decoration:none;position:relative}
.cite::after{content:"";position:absolute;inset:-6px -3px}
.cite:hover,.cite:focus-visible{background:var(--ink);color:var(--bg)}
a:focus-visible{outline:2px solid var(--ink);outline-offset:2px}
.t-main{flex:1}.fmt{display:inline-flex;border:1px solid var(--line);border-radius:999px;padding:3px;gap:2px;margin-top:4px;flex:none}
.fmt a{font-size:13px;font-weight:500;text-decoration:none;padding:4px 12px;border-radius:999px;color:var(--ink-2)}
.fmt a[aria-current]{background:var(--ink);color:var(--bg)}.fmt a:not([aria-current]):hover{color:var(--ink)}
.b-grid{display:grid;grid-template-columns:3fr 2fr;gap:32px}.b-grid.b-even{grid-template-columns:1fr 1fr}
.promise-s{font-size:16px;font-weight:500;margin-bottom:12px}
.b-pillars,.b-chan,.b-sv,.b-chg{list-style:none;margin:0;padding:0;display:grid;gap:8px;font-size:14px}
.b-pillars li{display:flex;justify-content:space-between;gap:12px;align-items:center;padding-top:8px;border-top:1px solid var(--line)}
.b-chan li,.b-sv li{display:flex;gap:10px;align-items:baseline}.b-chan .pill,.b-sv .pill{min-width:96px;text-align:center;flex:none}
.b-chg li{display:grid;grid-template-columns:132px 1fr;gap:12px}.b-pillars li>span:last-child{white-space:nowrap;flex:none}.b-chg time{color:var(--ink-2);font-size:13px;font-variant-numeric:tabular-nums;white-space:nowrap}
.b-ins{gap:8px;font-size:14.5px}.b-foot{font-size:13px;color:var(--ink-2);display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap}
.b-foot a{color:var(--ink);font-weight:600}
@media (max-width:720px){.b-grid,.b-grid.b-even{grid-template-columns:1fr;gap:20px}.top{flex-wrap:wrap}.t-main{flex-basis:calc(100% - 28px)}.fmt{margin-left:28px}}
@media (max-width:720px){main{padding:20px 16px 48px}.two,.sa,.foot{grid-template-columns:1fr}
.timeline li,.b-chg li{grid-template-columns:1fr;gap:2px}table.grid thead{display:none}
table.grid tr{display:grid;padding:10px 0;border-top:1px solid var(--line)}.grid th,.grid td{border:0;padding:2px 0}.grid tbody th{white-space:normal}}
@media print{body{font-size:12px}main{padding:0}section{break-inside:avoid}.tldr,.lens,.steal,.avoid{background:none;border:1px solid #ccc}
.cite{background:none;padding:0}.refs .u{font-size:9px}}
"""


def main(domain, do_lint=True):
    a = json.loads((ROOT / "data" / domain / "analysis.json").read_text(encoding="utf-8"))
    if do_lint:
        errs, n = lint(a, domain)
        if errs:
            print(f"LINT FAILED ({len(errs)}):")
            for e in errs:
                print("  -", e)
            sys.exit(1)
        print(f"lint ok: {n} evidence entries")
    sources = []
    for key in SOURCE_LABELS:
        f = ROOT / "data" / domain / f"{key}.json"
        s = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"status": "unavailable", "note": "not run"}
        sources.append({"source": key, "status": s["status"], "note": s.get("note", "")})
    title = f"{a.get('company')}: marketing OSINT"
    import dossier as DZ  # late import: dossier imports build
    for name, fn in (("index.html", DZ.render), ("full.html", render)):
        body, nrefs = fn(a, sources)
        dz = name == "index.html"
        page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="robots" content="noindex">
{BR.HEAD}
<style>{CSS}{CH.CSS}{EXTRA_CSS}{DZ.CSS if dz else ""}</style></head><body><main{' class="dz-main"' if dz else ""}>
{body}
</main><script>addEventListener("beforeprint",()=>document.querySelectorAll("details").forEach(d=>d.open=true));{CH.JS}{DZ.JS if dz else ""}</script></body></html>"""
        if "\u2014" in page:
            sys.exit(f"em dash in rendered {name}")
        out = ROOT / "output" / domain / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page, encoding="utf-8")
        print(f"wrote {out} ({len(page) // 1024} KB, {nrefs} sources cited)")
    ai = RC.ai_answers_page(domain, a.get("company"))
    if ai:
        _, body = ai
        page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(a.get("company"))}: raw AI answers</title><meta name="robots" content="noindex">
{BR.HEAD}
<style>{CSS}{CH.CSS}{EXTRA_CSS}</style></head><body><main class="ai-page">
<p><a href="full.html">Back to the detailed report</a></p><h1>Raw AI answers</h1>
<p class="meta">Same prompts sent to each model on the run date. Answers marked "no web search" come from model memory.</p>
{body}</main></body></html>"""
        (ROOT / "output" / domain / "ai_answers.html").write_text(page, encoding="utf-8")
        print("wrote ai_answers.html")


if __name__ == "__main__":
    main(sys.argv[1], "--no-lint" not in sys.argv)
