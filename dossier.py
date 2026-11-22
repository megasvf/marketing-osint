"""Company dossier (index.html): passport, who they sell to, how they market, what they say,
how they make money, momentum, reputation, strengths and weaknesses, what it means for me.

Reads the same analysis.json as the detailed report plus the dossier keys written by
prompts/dossier_enrich.md (passport, pricing_ladder, audience.segments[].level, relationships, for_me).
Every block degrades to nothing when its data is missing.
"""
import re

import build as B
from design import brand as BR
import charts as CH
import reader as RD
import report_charts as RC

esc, first = B.esc, B.first_sentence

REL_LABEL = {"competitor": "Competitor", "benchmark": "Benchmark", "prospect": "Potential client",
             "partner": "Partner", "self": "Own company"}
REL_HEAD = {"competitor": "As a competitor", "benchmark": "Worth borrowing", "prospect": "As a potential client",
            "partner": "As a partner", "self": "What the outside view says"}
LEVELS = [("primary", "Primary"), ("secondary", "Secondary"), ("emerging", "Emerging")]
EFFORT = {"heavy": 3, "active": 2, "light": 1, "not observed": 0}
COUNTRIES = {"US": "United States", "IN": "India", "GB": "United Kingdom", "UK": "United Kingdom", "DE": "Germany",
             "ES": "Spain", "FR": "France", "UA": "Ukraine", "BR": "Brazil", "CA": "Canada", "IT": "Italy",
             "NL": "Netherlands", "PL": "Poland", "AU": "Australia", "MX": "Mexico", "TR": "Turkey", "JP": "Japan",
             "RU": "Russia", "ID": "Indonesia", "PH": "Philippines", "PK": "Pakistan", "VN": "Vietnam",
             "KR": "South Korea", "AR": "Argentina", "CO": "Colombia", "PT": "Portugal", "SE": "Sweden", "IL": "Israel"}
SECTIONS = [("passport", "Passport"), ("bottom-line", "Bottom line"), ("audience", "Who they sell to"),
            ("marketing", "How they market"), ("messaging", "What they say"), ("money", "How they make money"),
            ("momentum", "Momentum"), ("reputation", "What others say"), ("swot", "Strengths and weaknesses"),
            ("for-me", "What it means for me")]


def sec(sid, title, body, lead=""):
    if not body:
        return ""
    lp = f'<p class="dz-lead">{lead}</p>' if lead else ""
    return f'<section class="dz-s" id="{sid}" aria-labelledby="{sid}-h"><h2 id="{sid}-h">{esc(title)}</h2>{lp}{body}</section>'


def head(a, sources):
    rel = a.get("relationships") or []
    chips = "".join(f'<span class="rel rel-{esc(r)}">{esc(REL_LABEL.get(r, r))}</span>' for r in rel)
    ok = sum(1 for s in sources if s["status"] == "ok")
    part = sum(1 for s in sources if s["status"] == "partial")
    cov = "".join(f'<li class="st-{esc(s["status"])}"><b></b>{esc(B.SOURCE_LABELS.get(s["source"], s["source"]))}</li>' for s in sources)
    tabs = ('<nav class="fmt" aria-label="Report format"><a href="index.html" aria-current="page">Dossier</a>'
            '<a href="full.html">Detailed</a></nav>')
    return f"""<header class="top dz-top">
  {BR.LOGO}
  <div class="t-main"><p class="kind">{BR.NAME} · company dossier</p>
  <h1>{esc(a.get("company"))} <span class="dom">{esc(a["domain"])}</span></h1>
  <p class="meta">Compiled {esc(a.get("generated"))} · public data only{f" · written for {esc(RD.name(a))}" if RD.name(a) else ""}</p>
  <div class="dz-rel">{chips}<details class="dz-cov"><summary>{ok} of {len(sources)} sources collected{f", {part} partial" if part else ""}</summary>
  <div class="coverage"><ul>{cov}</ul><p class="legend"><span class="st-ok"><b></b>collected</span><span class="st-partial"><b></b>partial</span>
  <span class="st-unavailable"><b></b>unavailable</span></p></div></details></div></div>
  {tabs}
</header>"""


def nav(present):
    li = "".join(f'<li><a href="#{sid}">{esc(t)}</a></li>' for sid, t in SECTIONS if sid in present)
    return f'<nav class="dz-nav" aria-label="Dossier sections"><ol>{li}</ol></nav>'


def passport(a, C):
    p = a.get("passport") or {}
    facts = p.get("facts") or []
    tag = p.get("tagline") or (a.get("company_card") or {}).get("positioning", {}).get("tagline")
    dl = "".join(f'<div class="pf{" pf-na" if (f.get("value") or "").lower() == "not public" else ""}"><dt>{esc(f.get("label"))}</dt>'
                 f'<dd>{esc(f.get("value"))}{C.refs((f.get("evidence") or [])[:1])}</dd></div>' for f in facts)
    out = f'<blockquote class="dz-tag">{esc(tag)}</blockquote>' if tag else ""
    if dl:
        out += f'<dl class="pfacts">{dl}</dl>'
    stats = B.key_stats(a, C)
    return out + (f'<div class="dz-stats">{stats}</div>' if stats else "")


def bottom_line(a, C):
    li = "".join(f"<li>{esc(t)}</li>" for t in a.get("tldr") or [])
    fm = a.get("for_me") or {}
    v = f'<p class="dz-verdict"><b>Why it matters{f" to {esc(RD.name(a))}" if RD.name(a) else ""}.</b> {esc(fm.get("verdict"))} <a href="#for-me">What to do</a></p>' if fm.get("verdict") else ""
    moves = []
    for r in a.get("relationships") or []:
        for p in ((fm.get("by_relationship") or {}).get(r) or {}).get("points", [])[:2]:
            if p.get("action"):
                chip = f'<span class="rel rel-{esc(r)}">{esc(REL_LABEL.get(r, r))}</span> ' if len(a.get("relationships") or []) > 1 else ""
                moves.append(f'<li>{chip}{esc(p["action"])}</li>')
    mv = f'<h3 class="lb-h">Top moves</h3><ul class="plain dz-moves">{"".join(moves[:4])}</ul>' if moves else ""
    return f'<ul class="dz-tldr">{li}</ul>{v}{mv}' if li else ""


def audience(a, C):
    segs = [s for s in (a.get("audience") or {}).get("segments") or []
            if not re.search(r"geograph|\bUS first\b", s.get("name") or "", re.I)]  # geography = the chart beside
    groups = []
    for lv, label in LEVELS:
        rows = [s for s in segs if s.get("level") == lv]
        if rows:
            li = "".join(f'<li><span class="sg-n">{esc(s.get("name"))}</span><span class="sg-s">{esc(first(s.get("signal")))}'
                         f'{C.refs((s.get("evidence") or [])[:1])}</span></li>' for s in rows)
            groups.append(f'<div class="sg sg-{lv}"><h3><span class="lvl lvl-{lv}">{label}</span></h3><ul>{li}</ul></div>')
    rest = [s for s in segs if s.get("level") not in dict(LEVELS)]
    if rest:
        li = "".join(f'<li><span class="sg-n">{esc(s.get("name"))}</span><span class="sg-s">{esc(first(s.get("signal")))}</span></li>' for s in rest)
        groups.append(f'<div class="sg"><h3>Segments</h3><ul>{li}</ul></div>')
    geo = ""
    d = RC.load(a["domain"], "similarweb")
    for i in (d or {}).get("items", []):
        cs = i.get("meta", {}).get("countries")
        if cs:
            geo = CH.hbar([(COUNTRIES.get(c["countryCode"], c["countryCode"]), c["sharePercentage"], None) for c in cs][:6],
                          "Where visitors come from", "%", note="SimilarWeb, share of visits, latest month.", src=i["url"])
    lines = ((a.get("company_card") or {}).get("audience") or {}).get("lines") or []
    dl = "".join(f'<div><dt>{esc(l.get("label"))}</dt><dd>{esc(l.get("value"))}</dd></div>' for l in lines
                 if (l.get("label") or "").lower() not in ("geos", "geography"))
    side = geo + (f'<dl class="dz-dl">{dl}</dl>' if dl else "")
    if not groups and not side:
        return ""
    return f'<div class="dz-2"><div class="sgs">{"".join(groups)}</div><div>{side}</div></div>'


def marketing(a, C):
    d = a["domain"]
    mo = a.get("motion") or {}
    chans = [c for c in a.get("channels") or [] if c.get("verdict") in EFFORT]
    chans.sort(key=lambda c: -EFFORT[c["verdict"]])
    eff = ""
    if chans:
        rows = "".join(f'<li><span class="ef-l">{esc(c["channel"])}</span><span class="ef-t" role="img" aria-label="{esc(c["verdict"])}">'
                       + "".join(f'<i class="{"on" if k < EFFORT[c["verdict"]] else ""}"></i>' for k in range(3))
                       + f'</span><span class="ef-v">{esc(c["verdict"])}</span></li>' for c in chans)
        eff = (f'<figure class="fig"><figcaption>Effort by channel</figcaption><ul class="effort">{rows}</ul>'
               f'<p class="fig-note">Judged from ads, pages, content and traffic signals; see the detailed report for evidence.</p></figure>')
    tr = RC.traffic(d)
    src_fig = tr[0] if tr else ""
    top = ""
    if mo.get("type") or mo.get("text"):
        mt = (mo.get("type") or "").replace("_", " ")
        top = (f'<p class="dz-motion"><span class="rel">{esc(mt[:1].upper() + mt[1:])} motion</span> '
               f'{esc(first(mo.get("text")))}</p>')
    gtm = ((a.get("company_card") or {}).get("gtm") or {}).get("lines") or []
    gl = "".join(f'<li><b>{esc(l.get("label"))}</b> {esc(l.get("value"))}</li>' for l in gtm)
    paid = RC.paid(d)
    figs = B.grid([eff, src_fig])
    lower = B.grid([f'<div><h3 class="lb-h">Channel by channel</h3><ul class="plain dz-gtm">{gl}</ul></div>' if gl else "",
                    paid[0] if paid else ""])
    return top + figs + lower


def messaging(a, C):
    pr, cc = a.get("promise") or {}, a.get("company_card") or {}
    ms = cc.get("messages") or {}
    pil = "".join(f'<li><span>{esc(p["name"])}</span>{B.meter(p["source_count"], p["sources_total"])}</li>' for p in a.get("pillars") or [])
    chips = "".join(f'<span class="chip">{esc(x)}</span>' for x in ms.get("proof") or [])
    tone = ", ".join(ms.get("tone") or [])
    ctas = "".join(f'<span class="cta">{esc(x)}</span>' for x in ms.get("ctas") or [])
    sv = "".join(f'<li><span class="pill v-{B.VERDICT.get(r.get("verdict"), "none")}">{esc(r.get("verdict"))}</span><span>{esc(r["claim"])}'
                 f'{C.refs((r.get("evidence") or [])[:1])}</span></li>' for r in a.get("say_vs_heard") or [])
    cg = "".join(f'<li><time>{esc(B.short_date(c.get("date")))}</time><span>{esc(first(c.get("after")))}{C.refs((c.get("evidence") or [])[:1])}</span></li>'
                 for c in (a.get("changes") or [])[:5])
    left = (f'<p class="promise-s">{esc(pr.get("text"))}{C.refs((pr.get("evidence") or [])[:1])}</p>' if pr.get("text") else "") + \
        (f'<h3 class="lb-h">Message pillars</h3><ul class="b-pillars">{pil}</ul>' if pil else "") + \
        (f'<h3 class="lb-h">Proof they use</h3><div class="chips-i">{chips}</div>' if chips else "") + \
        (f'<p class="cs"><span class="cl">Tone</span> {esc(tone)}</p>' if tone else "") + \
        (f'<p class="cs dz-ctas"><span class="cl">CTAs</span> {ctas}</p>' if ctas else "")
    right = (f'<h3 class="lb-h">Do customers agree?</h3><ul class="b-sv">{sv}</ul>' if sv else "") + \
        (f'<h3 class="lb-h">Recent changes</h3><ul class="b-chg">{cg}</ul>' if cg else "")
    return f'<div class="dz-2"><div>{left}</div><div>{right}</div></div>' if (left or right) else ""


def money(a, C):
    pl = a.get("pricing_ladder") or {}
    plans = pl.get("plans") or []
    fig = ""
    num = lambda v: isinstance(v, (int, float))
    shown = lambda p: p["price"] if num(p.get("price")) else (p.get("price_yearly") if num(p.get("price_yearly")) else None)
    priced = [p for p in plans if shown(p) is not None]
    if priced:
        groups = {}
        for p in plans:
            groups.setdefault(p.get("product") or "", []).append(p)
        rows = []
        for prod, ps in groups.items():
            vmax = max([shown(q) for q in ps if shown(q) is not None] or [1]) or 1
            if len(groups) > 1:
                rows.append(f'<p class="lad-g">{esc(prod)}</p>')
            for p in ps:
                lab = p.get("plan")
                v = shown(p)
                if v is not None:
                    w = max(0.5, 100 * v / vmax)
                    val = "Free" if v == 0 else f'${v:,.0f}/mo' + ("" if num(p.get("price")) else " (yearly)")
                    bar = f'<span class="hb-t"><i style="width:{w:.1f}%"></i></span>'
                else:
                    val, bar = "Quote", '<span class="hb-t hb-q"></span>'
                seats = (p.get("seats") or "").strip()
                if seats.lower() in ("not stated", "n/a", "unknown"):
                    seats = ""
                elif seats[:1].isdigit() and not any(w in seats for w in ("seat", "member", "user")):
                    seats += " seats"
                extra = "; ".join(x for x in (f'${p["price_yearly"]:,.0f} per month billed yearly' if num(p.get("price_yearly")) and p.get("price") else "",
                                              seats) if x)
                cite = C.refs((p.get("evidence") or [])[:1])
                note = "; ".join(x for x in (extra, p.get("note") or "") if x)
                rows.append(f'<div class="hb-row" title="{esc(prod)} {esc(lab)}: {esc(val)}. {esc(note)}"><span class="hb-l lad-l">{esc(lab)}'
                            f'{f"<small>{esc(note)}</small>" if note else ""}</span>{bar}<span class="hb-v">{esc(val)}{cite}</span></div>')
        tbl = CH.table(["Product", "Plan", "Billed monthly", "Billed yearly (per month)", "Seats", "Note"],
                       [(p.get("product"), p.get("plan"), p.get("price"), p.get("price_yearly"), p.get("seats"), p.get("note")) for p in plans])
        fig = CH.figure(f'Price ladder ({pl.get("currency", "USD")}, {pl.get("basis", "per month")})',
                        f'<div class="hbar ladder">{"".join(rows)}</div>', pl.get("note") or "", None, tbl)
    cc = a.get("company_card") or {}
    dup = {"products", "entry price", "motion", "sales motion", "pricing model"} if (a.get("passport") or {}).get("facts") else set()
    model = "".join(f'<div><dt>{esc(l.get("label"))}</dt><dd>{esc(l.get("value"))}</dd></div>' for l in (cc.get("model") or {}).get("lines") or []
                    if (l.get("label") or "").lower() not in dup)
    eco = "".join(f'<div class="pf{" pf-na" if "not public" in (r.get("value") or "") else ""}"><dt>{esc(r.get("label"))}</dt>'
                  f'<dd><b>{esc(r.get("value"))}</b>{f" <small>{esc(r.get(chr(110) + chr(111) + chr(116) + chr(101)))}</small>" if r.get("note") else ""}</dd></div>'
                  for r in (cc.get("economics") or {}).get("rows") or [])
    side = f'<h3 class="lb-h">Business model</h3><dl class="dz-dl">{model}</dl>' if model else ""
    nums = f'<h3 class="lb-h">Public numbers</h3><dl class="pfacts pf-eco">{eco}</dl>' if eco else ""
    if not (fig or side or nums):
        return ""
    top = f'<div class="dz-2"><div>{fig}</div><div>{side}</div></div>' if fig else (f'<div>{side}</div>' if side else "")
    return top + nums


def momentum(a, C):
    d = a["domain"]
    line, mt, mv = RC.headline_traffic(d), RC.momentum_table(d), B.moves_block(a, C)
    if not (line or mt or mv):
        return ""
    return line + (f'<div class="dz-2"><div>{mt}</div><div>{mv}</div></div>' if (mt or mv) else "")


def reputation(a, C):
    d = a["domain"]
    rt = RC.ratings(d)
    ai_f = RC.ai(d, a.get("company", ""))
    ai_t = a.get("ai_visibility") or {}
    txt = f'<p class="dz-note">{esc(first(ai_t.get("text")))}{C.refs((ai_t.get("evidence") or [])[:1])}</p>' if ai_t.get("text") else ""
    figs = B.grid([rt, (ai_f[0] if ai_f else "") + txt])
    return figs


def for_me(a, C):
    fm = (a.get("for_me") or {}).get("by_relationship") or {}
    rel = a.get("relationships") or list(fm)
    blocks = []
    for r in rel:
        x = fm.get(r) or {}
        pts = "".join(f'<li><p>{esc(p.get("text"))}{C.refs((p.get("evidence") or [])[:1])}</p>'
                      + (f'<p class="act"><b>Do:</b> {esc(p.get("action"))}</p>' if p.get("action") else "") + "</li>"
                      for p in x.get("points") or [])
        extra = ""
        if r == "competitor":
            extra = demote(B.battlecard_block(a, C, compact=True).replace('<section class="battle">', '<div class="battle dz-sub">').replace("</section>", "</div>"))
        elif r in ("benchmark", "self"):
            extra = demote(B.briefs_block(a, C, compact=True).replace('<section class="card">', '<div class="card dz-sub">').replace("</section>", "</div>"))
        elif r == "prospect":
            extra = prospect_block(x, C)
        elif r == "partner":
            extra = partner_block(x, C)
        if pts or extra:
            summ = f'<p class="dz-lead">{esc(x.get("summary"))}</p>' if x.get("summary") else ""
            blocks.append(f'<div class="fm fm-{esc(r)}"><h3 class="fm-h"><span class="rel rel-{esc(r)}">{esc(REL_LABEL.get(r, r))}</span> '
                          f'{esc(REL_HEAD.get(r, r))}</h3>{summ}{f"<ol class=fm-pts>{pts}</ol>" if pts else ""}{extra}</div>')
    return "".join(blocks)


def demote(h):
    return h.replace("<h3", "<h5").replace("</h3>", "</h5>").replace("<h2", "<h4").replace("</h2>", "</h4>")


def prospect_block(x, C):
    fit = x.get("fit") or []
    tr = "".join(f'<tr><th scope="row">{esc(f.get("criterion"))}</th><td><span class="pill v-{ {"yes": "ok", "partly": "warn", "no": "bad"}.get(f.get("verdict"), "none") }">'
                 f'{esc(f.get("verdict") or "unknown")}</span></td><td>{esc(f.get("text"))}{C.refs((f.get("evidence") or [])[:1])}</td></tr>' for f in fit)
    buyers = "".join(f'<li><b>{esc(b.get("role"))}</b> {esc(b.get("why"))}</li>' for b in x.get("buyers") or [])
    pains = "".join(f'<li>{esc(p.get("text"))}{C.refs((p.get("evidence") or [])[:1])}</li>' for p in x.get("pains") or [])
    ang = x.get("angle") or {}
    who = f"{esc(RD.name())}'s" if RD.name() else "your"
    out = f'<h4 class="lb-h">Fit with {who} ideal customer</h4><div class="tw"><table class="grid small">{tr}</table></div>' if tr else ""
    out += B.grid([f'<div><h4 class="lb-h">Who would buy</h4><ul class="plain">{buyers}</ul></div>' if buyers else "",
                   f'<div><h4 class="lb-h">Pains we can see</h4><ul class="plain">{pains}</ul></div>' if pains else ""])
    if ang.get("text"):
        out += f'<p class="dz-verdict"><b>Way in.</b> {esc(ang["text"])}</p>'
    return out


def partner_block(x, C):
    ov = "".join(f'<li>{esc(o.get("text"))}{C.refs((o.get("evidence") or [])[:1])}</li>' for o in x.get("overlap") or [])
    ideas = "".join(f'<li><b>{esc(i.get("title"))}.</b> {esc(i.get("body"))}{f" <span class=small-n>({esc(i.get(chr(117) + chr(110) + chr(105) + chr(116)))})</span>" if i.get("unit") else ""}</li>'
                    for i in x.get("ideas") or [])
    risks = "".join(f'<li>{esc(r.get("text"))}</li>' for r in x.get("risks") or [])
    return B.grid([f'<div><h4 class="lb-h">Shared audience</h4><ul class="plain">{ov}</ul></div>' if ov else "",
                   f'<div><h4 class="lb-h">What we could do together</h4><ul class="plain">{ideas}</ul></div>' if ideas else "",
                   f'<div><h4 class="lb-h">Risks</h4><ul class="plain">{risks}</ul></div>' if risks else ""])


def render(a, sources):
    C = B.Cites()
    parts = {
        "passport": passport(a, C), "bottom-line": bottom_line(a, C), "audience": audience(a, C),
        "marketing": marketing(a, C), "messaging": messaging(a, C), "money": money(a, C),
        "momentum": momentum(a, C), "reputation": reputation(a, C),
        "swot": B.swot_block(a, C, compact=True).replace("<section>", "").replace("</section>", "").split("</h2>", 1)[-1],
        "for-me": for_me(a, C),
    }
    present = [k for k, v in parts.items() if v]
    body = "".join(sec(sid, t, parts[sid]) for sid, t in SECTIONS if parts.get(sid))
    gaps = ", ".join(esc(B.SOURCE_LABELS.get(g["source"], g["source"])) for g in a.get("gaps") or [])
    n_ev = len(list(B.walk_evidence(a)))
    foot = (B.cost_block(a["domain"], compact=True) +
            f'<footer class="b-foot"><p><b>Gaps:</b> {gaps or "none"}.</p>'
            f'<p><a href="full.html">Detailed report with all {n_ev} evidence links</a></p></footer>')
    html = f'{head(a, sources)}<div class="dz">{nav(present)}<div class="dz-body">{body}{foot}</div></div>'
    return html, len(C.order)


CSS = """
main.dz-main{max-width:1200px}
.dz{display:grid;grid-template-columns:176px minmax(0,1fr);gap:40px;align-items:start}
.dz-nav{position:sticky;top:16px;font-size:13px}.dz-nav ol{list-style:none;margin:0;padding:0;display:grid;gap:2px;counter-reset:s}
.dz-nav a{display:block;padding:6px 10px;border-radius:6px;text-decoration:none;color:var(--ink-2)}
.dz-nav a:hover{background:var(--surf);color:var(--ink)}.dz-nav a.on{background:var(--surf);color:var(--ink);font-weight:600}
.dz-top{border-bottom:1px solid var(--line);margin-bottom:8px}
.dz-rel{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:10px}
.rel{display:inline-block;font-size:12px;font-weight:600;padding:2px 9px;border-radius:999px;background:var(--surf);color:var(--ink);white-space:nowrap}
.rel-competitor{background:var(--bad-bg);color:var(--bad)}.rel-benchmark{background:var(--ok-bg);color:var(--ok)}
.rel-prospect{background:var(--warn-bg);color:var(--warn)}.rel-partner{background:var(--surf);color:var(--s1)}
.dz-cov summary{cursor:pointer;font-size:12px;color:var(--ink-2);list-style:none}.dz-cov summary::-webkit-details-marker{display:none}
.dz-cov summary::after{content:" \\25BE"}.dz-cov[open] .coverage{margin-top:10px}
.dz-s{scroll-margin-top:16px}.dz-s h2{font-size:21px;margin-bottom:14px}
.dz-lead{color:var(--ink-2);margin:-6px 0 14px}
.dz-tag{margin:0 0 18px;font-size:20px;line-height:1.35;font-weight:600;letter-spacing:-.01em;max-width:46ch;text-wrap:balance}
.dz-tag::before{content:"\\201C"}.dz-tag::after{content:"\\201D"}
.pf-eco{margin-top:4px}.pf-eco small{color:var(--ink-2);font-weight:400;font-size:12px}
.pfacts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:0;margin:0 0 18px;border-top:1px solid var(--line)}
.pf{padding:10px 16px 10px 0;border-bottom:1px solid var(--line);min-width:0}
.pf dt,.dz-dl dt{font-size:12px;color:var(--ink-2);margin-bottom:2px}.pf dd,.dz-dl dd{margin:0;font-size:14px;font-weight:500}
.pf-na dd,.dz-dl .pf-na dd{color:var(--ink-2);font-weight:400}
.dz-stats .stats{margin:0}
.dz-tldr{margin:0;padding-left:20px;display:grid;gap:8px;font-size:16px;max-width:75ch}
.dz-verdict{margin-top:16px;background:var(--surf);border-radius:10px;padding:14px 18px;font-size:15px;max-width:none}
.dz-verdict a{font-weight:600;white-space:nowrap}.dz-moves{gap:8px;font-size:14.5px}.dz-moves .rel{margin-right:6px}
.dz-2{display:grid;grid-template-columns:minmax(0,3fr) minmax(0,2fr);gap:36px}.dz-2.dz-even{grid-template-columns:1fr 1fr}
.sgs{display:grid;gap:16px}.sg h3{margin-bottom:8px}.sg ul{list-style:none;margin:0;padding:0;display:grid;gap:10px}
.sg li{display:grid;gap:2px}.sg-n{font-weight:600;font-size:14.5px}.sg-s{font-size:13.5px;color:var(--ink-2)}
.lvl{font-size:12px;font-weight:600;padding:2px 9px;border-radius:999px}
.lvl-primary{background:var(--ink);color:var(--bg)}.lvl-secondary{box-shadow:inset 0 0 0 1px var(--ink-2);color:var(--ink)}
.lvl-emerging{box-shadow:inset 0 0 0 1px var(--line);color:var(--ink-2)}
.dz-dl{margin:0;display:grid;gap:8px}.dz-dl small{color:var(--ink-2);font-weight:400}
.dz-motion{margin-bottom:16px;max-width:none}.dz-motion .rel{margin-right:6px}
.dz .b-chg li{grid-template-columns:1fr;gap:0}
.effort{list-style:none;margin:0;padding:0;display:grid;gap:7px}
.effort li{display:grid;grid-template-columns:minmax(0,1fr) 66px 84px;gap:10px;align-items:center;font-size:13px}
.ef-l{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.ef-t{display:flex;gap:3px}
.ef-t i{height:12px;flex:1;border-radius:3px;background:var(--line)}.ef-t i.on{background:var(--s1)}
.ef-v{color:var(--ink-2);font-size:12px}
.dz-gtm{font-size:13.5px;gap:8px}
.dz-ctas{display:flex;flex-wrap:wrap;gap:6px;align-items:baseline}.cta{font-size:12px;font-weight:600;padding:2px 9px;border-radius:6px;box-shadow:inset 0 0 0 1px var(--ink-2)}
.ladder{gap:9px}.ladder .hb-row{grid-template-columns:minmax(0,46%) 1fr auto;align-items:start}.ladder .hb-t{margin-top:4px}.lad-l{white-space:normal;font-weight:500}.lad-l small{display:block;font-weight:400;color:var(--ink-2);font-size:12px;line-height:1.35}.hb-q{border-top:2px dashed var(--line);height:0;align-self:center}.ladder .lad-g{margin:10px 0 0;font-size:12px;color:var(--ink-2);font-weight:600}.ladder .lad-g:first-child{margin-top:0}
.dz h4,.dz h5{margin:0}.ct h5{font-size:13px;color:var(--ink-2);font-weight:600;margin:0 0 8px}
.dz-note{font-size:13px;color:var(--ink-2);margin-top:4px}
.fm{padding:18px 0;border-top:1px solid var(--line)}.fm:first-child{border-top:0;padding-top:0}
.fm-h{font-size:16px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:10px}
.fm-pts{margin:0 0 8px;padding-left:22px;display:grid;gap:12px;font-size:14.5px}.fm-pts .act{font-size:13px;color:var(--ink-2);margin-top:2px}
.fm-pts .act b{color:var(--ok)}
.dz-sub{margin-top:14px}.dz-sub>h4{font-size:15px;margin-bottom:10px}
.dz-body>footer{padding:20px 0;border-top:1px solid var(--line)}
@media (max-width:980px){.dz{grid-template-columns:1fr;gap:0}
.dz-nav{position:sticky;top:0;z-index:2;background:var(--bg);margin:0 -16px;padding:8px 16px;border-bottom:1px solid var(--line);overflow-x:auto}
.dz-nav ol{display:flex;gap:4px;width:max-content}.dz-nav a{white-space:nowrap;padding:5px 10px}
.dz-s{scroll-margin-top:56px}}
@media (max-width:720px){.pfacts{grid-template-columns:1fr 1fr}.dz-2{grid-template-columns:1fr;gap:20px}.dz-tag{font-size:18px}
.effort li{grid-template-columns:minmax(0,1fr) 54px 74px}}
@media print{.dz{display:block}.dz-nav{display:none}}
"""

JS = """
(function(){const links=[...document.querySelectorAll('.dz-nav a')];if(!links.length||!('IntersectionObserver' in window))return;
const map=new Map(links.map(a=>[a.getAttribute('href').slice(1),a]));
const io=new IntersectionObserver(es=>{es.forEach(e=>{if(e.isIntersecting){links.forEach(l=>l.classList.remove('on'));const a=map.get(e.target.id);if(a){a.classList.add('on');
const n=a.closest('nav');if(n.scrollWidth>n.clientWidth)n.scrollTo({left:a.offsetLeft-n.clientWidth/2+a.offsetWidth/2,behavior:'smooth'});}}})},{rootMargin:'-20% 0px -70% 0px'});
document.querySelectorAll('.dz-s').forEach(s=>io.observe(s));})();
"""
