"""Chart primitives for the OSINT report: HTML bars, SVG lines/timeline, stat rows, data tables.

Rules (dataviz skill): one axis, thin marks (bars <= 22px, 4px rounded data-end, 2px lines,
r >= 4 end dots with a 2px surface ring), recessive hairline grid, text in ink tokens (never the
series color), legend + direct labels for >= 2 series, a table view under every chart,
hover tooltips. Colors are CSS custom properties defined in build.CSS (light + dark).
"""
import html
import json
from datetime import date

SERIES = ["var(--s1)", "var(--s2)", "var(--s3)"]  # blue, orange, violet: validated (light + dark, all pairs, CVD ΔE >= 24)


def esc(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def fmt(v, unit=""):
    if v is None:
        return "n/a"
    if isinstance(v, float) and not v.is_integer():
        s = f"{v:,.1f}"
    else:
        v = int(round(v))
        if abs(v) >= 10000:
            k = v / 1000
            s = f"{k:,.0f}k" if abs(k) >= 100 or float(k).is_integer() else f"{k:,.1f}k"
        else:
            s = f"{v:,}"
    return f"{s}{unit}"


def table(headers, rows, caption="Data table"):
    th = "".join(f"<th>{esc(h)}</th>" for h in headers)
    tr = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in rows)
    return (f'<details class="dt"><summary>{esc(caption)}</summary>'
            f'<table class="grid small"><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></details>')


def figure(title, body, note="", src=None, tbl=""):
    s = f' <a class="fig-src" href="{esc(src)}">source</a>' if src else ""
    n = f'<p class="fig-note">{esc(note)}{s}</p>' if (note or src) else ""
    return f'<figure class="fig"><figcaption>{esc(title)}</figcaption>{body}{n}{tbl}</figure>'


def hbar(rows, title, unit="", highlight=None, max_rows=10, domain_max=None, note="", src=None, value_fmt=None):
    """rows: [(label, value, extra_label_or_None)]. Single series; `highlight` label gets --s1, others neutral."""
    rows = [r for r in rows if r[1] is not None][:max_rows]
    if not rows:
        return ""
    vmax = domain_max or max(r[1] for r in rows) or 1
    out = []
    for label, v, extra in rows:
        w = max(0.5, 100 * v / vmax)
        cls = "hl" if (highlight is None or (highlight and highlight.lower() in str(label).lower())) else "mut"
        val = value_fmt(v) if value_fmt else fmt(v, unit)
        tip = f"{label}: {val}" + (f" ({extra})" if extra else "")
        out.append(f'<div class="hb-row" title="{esc(tip)}"><span class="hb-l">{esc(label)}</span>'
                   f'<span class="hb-t"><i class="{cls}" style="width:{w:.1f}%"></i></span>'
                   f'<span class="hb-v">{esc(val)}{f" <small>{esc(extra)}</small>" if extra else ""}</span></div>')
    tbl = table(["Item", "Value", "Note"], [(l, value_fmt(v) if value_fmt else fmt(v, unit), e or "") for l, v, e in rows])
    return figure(title, f'<div class="hbar">{"".join(out)}</div>', note, src, tbl)


def columns(points, title, unit="", note="", src=None):
    """Monthly counts: [(label 'YYYY-MM', value)] as vertical HTML columns."""
    if not points:
        return ""
    vmax = max(v for _, v in points) or 1
    cols = "".join(
        f'<div class="col" title="{esc(l)}: {fmt(v, unit)}"><span class="col-v">{fmt(v) if v else ""}</span>'
        f'<i style="height:{max(2, 100 * v / vmax):.0f}%"></i><span class="col-l">{esc(l[2:] if len(l) == 7 else l)}</span></div>'
        for l, v in points)
    return figure(title, f'<div class="cols">{cols}</div>', note, src, table(["Month", "Count"], [(l, v) for l, v in points]))


def _ticks(vmin, vmax, n=4):
    span = vmax - vmin or 1
    raw = span / n
    mag = 10 ** (len(str(int(raw))) - 1) if raw >= 1 else 1
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    lo = (vmin // step) * step
    out, t = [], lo
    while True:  # last tick must cover the data maximum
        out.append(t)
        if t >= vmax:
            break
        t += step
    return out


def short(name):
    """'example.org' -> 'example' for direct labels."""
    return name.split(".")[0] if name and "." in name and " " not in name else name


MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def _xticks(dates, n_lab):
    """Calendar-aligned month ticks (every 1/2/3/6/12 months from January), at most n_lab; falls back to even spacing."""
    first = {}
    for d in dates:
        first.setdefault(d[:7], d)
    months = list(first)
    for step in (1, 2, 3, 6, 12):
        pick = [m for m in months if (int(m[5:7]) - 1) % step == 0]
        if 2 <= len(pick) <= n_lab:
            return [(first[m], f"{MONTHS[int(m[5:7]) - 1]} {m[:4]}" if step < 12 else m[:4]) for m in pick]
    idx = sorted({round(k * (len(dates) - 1) / max(1, n_lab - 1)) for k in range(n_lab)})
    return [(dates[i], dates[i][:7]) for i in idx]


def line(series, title, unit="", note="", src=None, height=220, width=640):
    """series: [{"name": str, "points": [("YYYY-MM-DD", value)]}], max 3, one shared y-axis."""
    series = [s for s in series if s.get("points")][:3]
    if not series:
        return ""
    longest = max(len(f"{short(s['name'])} {fmt(s['points'][-1][1], unit)}") for s in series)
    W, H, L, T, B = width, height, 44, 14, 28
    R = 18 + int(longest * (7.4 if width >= 600 else 6.8))
    dates = sorted({d for s in series for d, _ in s["points"]})
    vals = [v for s in series for _, v in s["points"] if v is not None]
    vmin = 0
    ticks = _ticks(vmin, max(vals))
    vmax = ticks[-1]
    x = {d: L + (W - L - R) * (i / max(1, len(dates) - 1)) for i, d in enumerate(dates)}

    def y(v):
        return T + (H - T - B) * (1 - (v - vmin) / ((vmax - vmin) or 1))
    g = "".join(f'<line class="gl" x1="{L}" x2="{W - R}" y1="{y(t):.1f}" y2="{y(t):.1f}"/>'
                f'<text class="ax" x="{L - 6}" y="{y(t) + 4:.1f}" text-anchor="end">{fmt(t)}</text>' for t in ticks)
    xl = "".join(f'<text class="ax" x="{x[d]:.1f}" y="{H - 8}" text-anchor="middle">{lab}</text>'
                 for d, lab in _xticks(dates, 6 if width >= 600 else 3))
    paths, ends, label_y = [], [], []
    for k, s in enumerate(series):
        pts = [(d, v) for d, v in s["points"] if v is not None]
        dpath = " ".join(f'{"M" if i == 0 else "L"}{x[d]:.1f},{y(v):.1f}' for i, (d, v) in enumerate(pts))
        c = SERIES[k]
        paths.append(f'<path d="{dpath}" fill="none" stroke="{c}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')
        d_end, v_end = pts[-1]
        ly = y(v_end) + 4
        for other in label_y:  # keep direct labels >= 15px apart
            if abs(ly - other) < 15:
                ly = other + (15 if ly >= other else -15)
        label_y.append(ly)
        ends.append(f'<circle cx="{x[d_end]:.1f}" cy="{y(v_end):.1f}" r="4.5" fill="{c}" stroke="var(--bg)" stroke-width="2"/>'
                    f'<text class="lab" x="{x[d_end] + 9:.1f}" y="{ly:.1f}">{esc(short(s["name"]))} {fmt(v_end, unit)}</text>')
    data = {"dates": dates, "series": [{"name": s["name"], "c": SERIES[k], "v": dict(s["points"])} for k, s in enumerate(series)]}
    svg = (f'<svg class="lc" viewBox="0 0 {W} {H}" role="img" aria-label="{esc(title)}" data-chart=\'{esc(json.dumps(data))}\' '
           f'data-geo="{L},{W - R},{T},{H - B},{vmin},{vmax}">{g}{xl}{"".join(paths)}{"".join(ends)}'
           f'<line class="xh" x1="0" x2="0" y1="{T}" y2="{H - B}"/></svg><div class="tt" hidden></div>')
    legend = ""
    if len(series) > 1:
        legend = '<p class="lg">' + "".join(f'<span><b style="background:{SERIES[k]}"></b>{esc(s["name"])}</span>'
                                            for k, s in enumerate(series)) + "</p>"
    rows = [(d, *[fmt(dict(s["points"]).get(d), unit) for s in series]) for d in dates]
    tbl = table(["Month"] + [s["name"] for s in series], rows)
    return figure(title, legend + f'<div class="lc-wrap">{svg}</div>', note, src, tbl)


def stats(items):
    """items: [{"label", "value", "sub", "trend": "up|down|flat|None", "href"}] -> compact figure row."""
    cells = []
    for it in items:
        arrow = {"up": "↑", "down": "↓", "flat": "→"}.get(it.get("trend"), "")
        sub = f'<span class="st-sub t-{esc(it.get("trend") or "none")}">{arrow} {esc(it.get("sub", ""))}</span>' if it.get("sub") else ""
        v = esc(it["value"])
        if it.get("href"):
            v = f'<a href="{esc(it["href"])}">{v}</a>'
        cells.append(f'<div class="st"><span class="st-l">{esc(it["label"])}</span><span class="st-v">{v}</span>{sub}</div>')
    n = len(cells)
    cols = n if n <= 4 else (3 if n in (5, 6) else 4)
    return f'<div class="stats" style="--n:{n};--c:{cols}">{"".join(cells)}</div>'


def timeline(events, title, note=""):
    """events: [{"date": "YYYY-MM-DD", "label": str, "href": str}] on one dated axis (SVG), labels alternate."""
    ev = sorted([e for e in events if e.get("date") and len(e["date"]) >= 7], key=lambda e: e["date"])
    if not ev:
        return ""
    def dnum(s):
        p = s.split("-") + ["15"]
        return date(int(p[0]), int(p[1]), int(p[2][:2]) if len(p) > 2 and p[2][:2].isdigit() else 15).toordinal()
    lo, hi = dnum(ev[0]["date"]), dnum(ev[-1]["date"])
    lo -= 20
    hi += 20
    W, H, L, R = 640, 150, 20, 20
    def x(s):
        return L + (W - L - R) * (dnum(s) - lo) / ((hi - lo) or 1)
    parts = [f'<line class="axl" x1="{L}" x2="{W - R}" y1="75" y2="75"/>']
    for i, e in enumerate(ev):
        up = i % 2 == 0
        xx = x(e["date"])
        ty = 40 if up else 112
        anchor = "start" if xx < W * 0.25 else ("end" if xx > W * 0.75 else "middle")
        lbl = e["label"] if len(e["label"]) <= 34 else e["label"][:32] + "…"
        parts.append(f'<g><title>{esc(e["date"])}: {esc(e["label"])}</title>'
                     f'<line class="gl" x1="{xx:.1f}" x2="{xx:.1f}" y1="{ty + (6 if up else -16):.0f}" y2="75"/>'
                     f'<circle cx="{xx:.1f}" cy="75" r="5" fill="var(--s1)" stroke="var(--bg)" stroke-width="2"/>'
                     f'<text class="ax" x="{xx:.1f}" y="{ty - 12 if up else ty + 2}" text-anchor="{anchor}">{esc(e["date"][:7])}</text>'
                     f'<text class="lab" x="{xx:.1f}" y="{ty + 2 if up else ty + 16}" text-anchor="{anchor}">{esc(lbl)}</text></g>')
    svg = f'<svg class="tl" viewBox="0 0 {W} {H}" role="img" aria-label="{esc(title)}">{"".join(parts)}</svg>'
    tbl = table(["Date", "Event"], [(e["date"], e["label"]) for e in ev])
    return figure(title, svg, note, None, tbl)


def chips(groups, title, note=""):
    """groups: {category: [tool, ...]} -> labelled chip rows."""
    if not groups:
        return ""
    rows = "".join(f'<div class="chip-row"><span class="chip-k">{esc(k)}</span>'
                   + "".join(f'<span class="chip">{esc(t)}</span>' for t in v) + "</div>" for k, v in groups.items())
    return figure(title, f'<div class="chips">{rows}</div>', note)


JS = """
document.querySelectorAll('svg.lc').forEach(svg=>{
  const d=JSON.parse(svg.dataset.chart), g=svg.dataset.geo.split(',').map(Number), [L,R,T,B,vmin,vmax]=g;
  const tt=svg.parentElement.querySelector('.tt'), xh=svg.querySelector('.xh'), n=d.dates.length;
  const xs=d.dates.map((_,i)=>L+(R-L)*(i/Math.max(1,n-1)));
  function show(ev){const r=svg.getBoundingClientRect(), vx=(ev.clientX-r.left)*(svg.viewBox.baseVal.width/r.width);
    let i=0,b=1e9; xs.forEach((x,k)=>{const dd=Math.abs(x-vx); if(dd<b){b=dd;i=k}});
    xh.setAttribute('x1',xs[i]); xh.setAttribute('x2',xs[i]); xh.style.opacity=1;
    const dt=d.dates[i]; tt.innerHTML='<b>'+dt.slice(0,7)+'</b>'+d.series.map(s=>'<span><i style="background:'+s.c+'"></i>'+s.name+': '+(s.v[dt]==null?'n/a':Number(s.v[dt]).toLocaleString())+'</span>').join('');
    tt.hidden=false; const px=xs[i]/svg.viewBox.baseVal.width*r.width; tt.style.left=Math.min(px+12,r.width-170)+'px';}
  svg.addEventListener('mousemove',show); svg.addEventListener('mouseleave',()=>{tt.hidden=true; xh.style.opacity=0});
});
"""

CSS = """
.fig{margin:0 0 20px;min-width:0}.fig figcaption{font-size:14px;font-weight:600;margin-bottom:10px}
.fig-note{font-size:12px;color:var(--ink-2);margin-top:8px}.fig-src{color:var(--ink-2)}
.figs{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px 32px}.figs>.fig:has(>.tw thead th:nth-child(4)){grid-column:1/-1}
.hbar{display:grid;gap:6px}.hb-row{display:grid;grid-template-columns:minmax(90px,38%) 1fr auto;gap:10px;align-items:center;font-size:13px}
.hb-l{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.hb-t{height:14px;display:block;position:relative}
.hb-t i{position:absolute;left:0;top:0;bottom:0;border-radius:0 4px 4px 0;background:var(--s1);min-width:2px}
.hb-t i.mut{background:var(--mut)}.hb-v{font-variant-numeric:tabular-nums;white-space:nowrap;font-weight:500;min-width:0;max-width:22ch;overflow-wrap:anywhere}.hb-v small{color:var(--ink-2);font-weight:400;white-space:normal}
.hb-row:hover .hb-t i{filter:brightness(1.12)}
.cols{display:flex;align-items:flex-end;gap:4px;height:140px;padding-top:16px}
.col{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;min-width:0}
.col i{display:block;width:min(22px,80%);background:var(--s1);border-radius:4px 4px 0 0}.col-v{font-size:11px;color:var(--ink-2)}
.col-l{font-size:10px;color:var(--ink-2);margin-top:4px;white-space:nowrap}
.lc-wrap{position:relative}.lc{width:100%;height:auto;display:block;overflow:visible}
.lc .gl,.tl .gl{stroke:var(--line);stroke-width:1}.ax{font-size:11px;fill:var(--ink-2)}.lab{font-size:12px;fill:var(--ink);font-weight:500}
.lc .xh{stroke:var(--ink-2);stroke-width:1;opacity:0}.axl{stroke:var(--ink-2);stroke-width:1}
.tt[hidden]{display:none}.tt{position:absolute;top:8px;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-size:12px;
display:grid;gap:3px;pointer-events:none;min-width:150px;box-shadow:0 2px 6px rgba(0,0,0,.08)}.tt i{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:6px}
.lg{display:flex;gap:16px;font-size:12px;color:var(--ink-2);margin-bottom:6px}.lg b{display:inline-block;width:10px;height:3px;border-radius:2px;margin-right:6px;vertical-align:middle}
.tl{width:100%;height:auto;display:block}
.stats{display:grid;grid-template-columns:repeat(var(--c),1fr);gap:1px;background:var(--line);border-radius:10px;overflow:hidden;margin:4px 0 8px}
.st{background:var(--bg);padding:12px 14px;display:grid;gap:2px}.st-l{font-size:12px;color:var(--ink-2)}
.st-v{font-size:22px;font-weight:700;font-variant-numeric:tabular-nums;letter-spacing:-.01em}.st-v a{text-decoration:none}
.st-sub{font-size:12px;color:var(--ink-2)}.t-up{color:var(--ok)}.t-down{color:var(--bad)}
.chips{display:grid;gap:8px}.chip-row{display:flex;flex-wrap:wrap;gap:6px;align-items:baseline}.chip-k{font-size:12px;color:var(--ink-2);min-width:120px}
.chip{font-size:12px;border:1px solid var(--line);border-radius:999px;padding:2px 9px}
.dt{margin-top:8px;font-size:12px}.dt summary{cursor:pointer;color:var(--ink-2)}.grid.small{font-size:12px;margin-top:6px}
@media (min-width:1000px){.stats{grid-template-columns:repeat(var(--n),1fr)}}
@media (max-width:720px){.stats{grid-template-columns:repeat(2,1fr)}.st:last-child:nth-child(odd){grid-column:span 2}}
@media print{.dt{display:none}.tt{display:none}}
"""
