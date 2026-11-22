"""Build the showcase and order site in English (public/) and Ukrainian (public/uk/).

  python site/build_site.py notion.com figma.com miro.com linear.app

Pages per language: index, order (order form or payment link), thanks (after payment), terms, privacy, refunds, contact.
Copy lives in site/content_en.py and site/content_uk.py; seller details, price and links in site/business.json
(git-ignored; see business.example.json). A missing value renders as a red "to fill" mark and is listed on stdout.
Example cards read data/<domain>/analysis.json; run build.py for each domain first. Delivered reports in public/r/
(made by deliver.py) are kept between builds. Styles use the shared design tokens (DESIGN.md).
"""
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import build as B  # noqa: E402
import content_en  # noqa: E402
from design import brand as BR  # noqa: E402

OUT = ROOT / "public"
esc = B.esc
PAGES = ["index", "order", "thanks", "terms", "privacy", "refunds", "contact"]
MISSING = set()


def languages():
    langs = [content_en]
    try:
        import content_uk
        langs.append(content_uk)
    except ImportError:
        print("note: site/content_uk.py not found, building English only")
    return langs


def business(lang):
    f = HERE / "business.json"
    d = json.loads((f if f.exists() else HERE / "business.example.json").read_text(encoding="utf-8"))
    out = {k: v for k, v in d.items() if not k.startswith("_") and not k.endswith("_uk")}
    if lang == "uk":
        out.update({k[:-3]: v for k, v in d.items() if k.endswith("_uk") and v})
    return out


OPTIONAL = {"mor_note"}  # may stay empty on purpose


class Ctx(dict):
    """format_map context: business values are escaped; a missing or empty one becomes a visible to-fill mark."""

    def __init__(self, data, todo):
        super().__init__({k: esc(v) for k, v in data.items() if v not in (None, "") or k in OPTIONAL})
        if self.get("mor_note"):
            self["mor_note"] = " " + self["mor_note"]
        self.todo = todo

    def __missing__(self, key):
        MISSING.add(key)
        return f'<mark class="todo">[{esc(self.todo)}: {esc(key)}]</mark>'


def fmt(s, ctx):
    return s.format_map(ctx) if "{" in s else s


# ---------------------------------------------------------------- shared chrome

def head(C, lang, page, title, description, prefix, noindex=False):
    other = [x for x in languages() if x.LANG != lang]
    alt = "".join(f'<link rel="alternate" hreflang="{x.HTML_LANG}" href="{prefix}{"" if x.LANG == "en" else x.LANG + "/"}{page}.html">' for x in other)
    return (f'<!doctype html><html lang="{C.HTML_LANG}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(title)}</title><meta name="claude:viewport-fit-sides" content="cover"><meta name="description" content="{esc(description)}">'
            + ('<meta name="robots" content="noindex">' if noindex else "") + alt
            + f'{BR.HEAD}<style>{BR.TOKENS}{CSS}</style></head><body>')


def switch_href(lang, page, prefix):
    """Link to the same page in the other language."""
    return f"{prefix}uk/{page}.html" if lang == "en" else f"{prefix}{page}.html"


def nav(C, lang, page, prefix):
    u = C.UI
    home = "" if page == "index" else "index.html"
    gh = f'<a href="{esc(BR.REPO_URL)}">{u["nav_github"]}</a>' if BR.REPO_URL else ""
    other = next((x for x in languages() if x.LANG != lang), None)
    sw = f'<a class="lang" href="{switch_href(lang, page, prefix)}" hreflang="{other.HTML_LANG}" lang="{other.HTML_LANG}">{u["lang_switch"]}</a>' if other else ""
    return (f'<header class="nav"><a class="brand" href="{home or "#top"}">{BR.LOGO}<span>{esc(BR.NAME)}</span></a>'
            f'<nav aria-label="Sections"><a href="{home}#examples">{u["nav_examples"]}</a><a href="{home}#how">{u["nav_how"]}</a>'
            f'<a href="{home}#sources">{u["nav_sources"]}</a>{gh}<a class="nav-order" href="order.html">{u["nav_order"]}</a>{sw}</nav></header>')


def foot(C, lang, page, prefix):
    u = C.UI
    other = next((x for x in languages() if x.LANG != lang), None)
    sw = f' · <a href="{switch_href(lang, page, prefix)}" lang="{other.HTML_LANG}">{u["lang_switch"]}</a>' if other else ""
    gh = f' · <a href="{esc(BR.REPO_URL)}">GitHub</a>' if BR.REPO_URL else ""
    return (f'<footer class="foot"><span class="fb">{BR.LOGO}{esc(BR.NAME)}</span>'
            f'<span class="muted"><a href="terms.html">{u["foot_terms"]}</a> · <a href="privacy.html">{u["foot_privacy"]}</a> · '
            f'<a href="refunds.html">{u["foot_refunds"]}</a> · <a href="contact.html">{u["foot_contact"]}</a>{sw}{gh} · AGPL-3.0</span></footer></body></html>')


# ---------------------------------------------------------------- home

def example(domain):
    a = json.loads((ROOT / "data" / domain / "analysis.json").read_text(encoding="utf-8"))
    srcs = [json.loads(f.read_text(encoding="utf-8")) for f in (ROOT / "data" / domain).glob("*.json")
            if not f.name.startswith("_") and f.name not in ("analysis.json", "changes.json")]
    return {"headless": (ROOT / "data" / domain / "_logs" / "factcheck_report.md").exists(), "domain": domain,
            "company": a.get("company") or domain, "line": (a.get("tldr") or [""])[0], "n_ev": len(list(B.walk_evidence(a))),
            "ok": sum(1 for s in srcs if s.get("status") == "ok"), "part": sum(1 for s in srcs if s.get("status") == "partial"),
            "gaps": [B.SOURCE_LABELS.get(g.get("source"), g.get("source")) for g in a.get("gaps") or []], "date": a.get("generated")}


def card(x, u, prefix):
    gaps = (f'<p class="ex-gap">{u["card_gaps"]}: {esc(", ".join(x["gaps"][:4]))}{" " + u["card_more"] if len(x["gaps"]) > 4 else ""}</p>'
            if x["gaps"] else "")
    ex = f'{prefix}examples/{esc(x["domain"])}'
    return (f'<article class="ex"><p class="ex-dom">{esc(x["domain"])}</p><h3>{esc(x["company"])}</h3>'
            f'<p class="ex-line" lang="en">{esc(x["line"])}</p>'
            f'<dl class="ex-n"><div><dt>{u["card_sources"]}</dt><dd>{x["ok"]}<small> + {x["part"]} {u["card_partial"]}</small></dd></div>'
            f'<div><dt>{u["card_evidence"]}</dt><dd>{x["n_ev"]}</dd></div></dl>{gaps}'
            f'<p class="ex-go"><a href="{ex}/index.html">{u["card_dossier"]}</a><a href="{ex}/full.html">{u["card_detailed"]}</a></p>'
            f'<p class="ex-date">{u["card_compiled"]} {esc(x["date"])} · '
            f'{u["card_headless"] if x["headless"] else u["card_manual"]}</p></article>')


def home(C, ctx, examples, lang, prefix):
    H, u = C.HOME, C.UI
    f = lambda s: fmt(s, ctx)  # noqa: E731
    free = "".join(f"<tr><th scope=row>{esc(n)}</th><td>{esc(w)}</td></tr>" for n, w in C.FREE)
    paid = "".join(f"<tr><th scope=row>{esc(n)}</th><td>{esc(w)}</td><td class=nw>{esc(c)}</td></tr>" for n, w, c in C.PAID)
    gates = "".join(f'<li><span class="code">{c}</span>{esc(t)}</li>' for c, t in C.GATES)
    dz = "".join(f"<li>{esc(t)}</li>" for t in C.DOSSIER)
    steps = "".join(f"<li><b>{esc(t)}</b><span>{esc(d)}</span></li>" for t, d in H["steps"])
    cards = "".join(card(x, u, prefix) for x in examples) or f'<p class="muted">{u["card_none"]}</p>'
    gh = esc(BR.REPO_URL)
    repo = f'{H["run_src"]} <a href="{gh}">{gh.replace("https://", "")}</a>' if gh else f'<span class="muted">{H["run_src_none"]}</span>'
    return (head(C, lang, "index", f(H["title"]), f(H["description"]), prefix) + nav(C, lang, "index", prefix) + f"""<main id="top">
<section class="hero"><p class="kicker">{f(H["kicker"])}</p><h1>{H["h1"]}</h1><p class="lede">{f(H["lede"])}</p>
<p class="cta"><a class="btn" href="#examples">{H["cta_examples"]}</a><a class="btn ghost" href="order.html">{H["cta_order"]}</a>
<a class="btn ghost" href="#run">{H["cta_run"]}</a>{f'<a class="btn ghost" href="{gh}">{H["cta_github"]}</a>' if gh else ""}</p></section>
<section id="examples"><h2>{H["ex_h"]}</h2><p class="sub">{f(H["ex_sub"])} {u["reports_english"] if lang != "en" else ""}</p><div class="exs">{cards}</div></section>
<section><h2>{H["get_h"]}</h2><div class="two"><div><h3>{H["get_dossier"]}</h3><ol class="dz">{dz}</ol></div>
<div><h3>{H["get_plus"]}</h3><ul class="plain">{"".join(f"<li>{x}</li>" for x in H["get_list"])}</ul></div></div></section>
<section id="how"><h2>{H["how_h"]}</h2><ol class="steps">{steps}</ol>
<div class="gate"><h3>{H["gate_h"]}</h3><ul class="codes">{gates}</ul></div>
<div class="caught"><h3>{H["caught_h"]}</h3><p class="sub">{H["caught_sub"]}</p><ul class="plain">{"".join(f"<li>{x}</li>" for x in H["caught"])}</ul>
<p class="sub">{H["caught_end"]}</p></div></section>
<section id="sources"><h2>{H["src_h"]}</h2><p class="sub">{H["src_sub"]}</p>
<h3>{H["src_free"]}</h3><div class="tw"><table class="grid"><tbody>{free}</tbody></table></div>
<h3>{H["src_paid"]}</h3><div class="tw"><table class="grid"><thead><tr>{"".join(f"<th>{esc(h)}</th>" for h in C.PAID_HEAD)}</tr></thead><tbody>{paid}</tbody></table></div>
<p class="sub">{H["src_end"]}</p></section>
<section><h2>{H["reader_h"]}</h2><div class="two"><p>{H["reader_p"]}</p>
<pre class="code-b">{{
 "name": "Acme Forms",
 "domain": "acmeforms.example",
 "pricing": [{{"plan": "Pro", "price": 29}}],
 "ideal_customer": ["Marketing team of 2 to 20"],
 "rules": ["CRMs are partners"]
}}</pre></div></section>
<section class="band"><div><h2>{H["order_band_h"]}</h2><p>{f(H["order_band_p"])}</p></div><a class="btn" href="order.html">{H["cta_order"]}</a></section>
<section id="run"><h2>{H["run_h"]}</h2><p class="sub">{H["run_sub"]}</p>
<pre class="code-b">pip install requests beautifulsoup4
python run_job.py example.com --brand Example --category "form builder"</pre><p>{repo}</p></section>
<section class="fine"><h2>{H["fine_h"]}</h2><ul class="plain">{"".join(f"<li>{f(x)}</li>" for x in H["fine"])}</ul></section>
</main>""" + foot(C, lang, "index", prefix))


# ---------------------------------------------------------------- order, thanks, legal

def order(C, ctx, lang, prefix):
    O, u = C.ORDER, C.UI
    f = lambda s: fmt(s, ctx)  # noqa: E731
    mode = business(lang).get("order_mode", "link")
    if mode == "email":
        buy = email_form(O["form"], O["email_mode"], ctx, lang)
    elif mode == "form":
        buy = order_form(O["form"], ctx, lang)
    else:
        link = ctx.get(f"payment_link_{lang}") or ctx.get("payment_link_en")
        buy = (f'<a class="btn big" href="{link}">{O["buy"]} · {ctx["price"]}</a>' if link
               else f'<span class="btn big off" aria-disabled="true">{O["buy_missing"]}</span>{ctx["payment_link_" + lang]}')
    pay = (O["pay_with_fields"] if business(lang).get("checkout_fields") == "yes" or business(lang).get("order_mode") == "form"
           else O["pay_without_fields"])
    steps = "".join(f"<li><b>{esc(t)}</b><span>{f(pay) if i == 0 else esc(d)}</span></li>" for i, (t, d) in enumerate(O["steps"]))
    if mode == "email":
        steps = "".join(f"<li><b>{esc(t)}</b><span>{f(d)}</span></li>" for t, d in O["email_mode"]["steps"])
    faq = "".join(f"<details><summary>{esc(q)}</summary><p>{f(a)}</p></details>" for q, a in O["faq"])
    return (head(C, lang, "order", f(O["title"]), f(O["description"]), prefix) + nav(C, lang, "order", prefix) + f"""<main id="top">
<section class="hero"><h1>{O["h1"]}</h1><p class="lede">{O["lede"]}</p>
<div class="buy"><dl class="terms3"><div><dt>{O["price_label"]}</dt><dd>{ctx["price"]}<small>{f(O["price_note"])}</small></dd></div>
<div><dt>{O["turn_label"]}</dt><dd>{f(O["turn_value"])}</dd></div><div><dt>{O["link_label"]}</dt><dd>{f(O["link_value"])}</dd></div></dl>
{buy}{"" if business(lang).get("order_mode") in ("form", "email") else f'<p class="consent">{O["consent"]}</p>'}<p class="muted small">{u["reports_english"]}</p></div></section>
<section><h2>{O["steps_h"]}</h2><ol class="steps s3">{steps}</ol></section>
<section><div class="two"><div><h2>{O["get_h"]}</h2><ul class="plain dots">{"".join(f"<li>{esc(x)}</li>" for x in O["get"])}</ul></div>
<div><h2>{O["sources_h"]}</h2><p>{f(O["sources_p"])}</p><h3>{O["not_h"]}</h3><ul class="plain dots">{"".join(f"<li>{esc(x)}</li>" for x in O["not"])}</ul></div></div></section>
<section><h2>{O["faq_h"]}</h2><div class="faq">{faq}</div></section>
</main>""" + foot(C, lang, "order", prefix))


def order_form(F, ctx, lang):
    """The order form posts to the Cloudflare Pages Function /api/order (functions/api/order.js),
    which creates the payment and redirects to the provider's page. Errors come back as ?error=<code>."""
    f = lambda s: fmt(s, ctx)  # noqa: E731
    opts = "".join(f'<option value="{v}">{esc(t)}</option>' for v, t in F["rels"])
    errs = "".join(f'<p class="err" data-code="{k}" hidden>{f(v)}</p>' for k, v in F["errors"].items())
    return f"""<form id="form" class="oform" method="post" action="/api/order" novalidate>{errs}
<input type="hidden" name="lang" value="{lang}">
<label for="f-domain">{F["domain"]}</label><input id="f-domain" name="domain" required inputmode="url" autocomplete="off" placeholder="{F["domain_ph"]}" maxlength="120">
<label for="f-rel">{F["rel"]}</label><select id="f-rel" name="relationship" required>{opts}</select>
<label for="f-notes">{F["notes"]}</label><input id="f-notes" name="notes" maxlength="300" placeholder="{esc(F["notes_ph"])}">
<label for="f-email">{F["email"]}</label><input id="f-email" name="email" type="email" required autocomplete="email" maxlength="200">
<div class="hp" aria-hidden="true"><label for="f-fax">Fax</label><input id="f-fax" name="company_fax" tabindex="-1" autocomplete="off"></div>
<label class="chk" for="f-consent"><input id="f-consent" type="checkbox" name="consent" value="yes" required><span>{F["consent"]}</span></label>
<button class="btn big" type="submit">{F["submit"]} · {ctx["price"]}</button><p class="muted small">{f(F["after"])}</p></form>
<script>(function(){{var c=new URLSearchParams(location.search).get("error");if(!c)return;var e=document.querySelector('.err[data-code="'+c+'"]')||document.querySelector('.err[data-code="form"]');if(e)e.hidden=false;}})();</script>"""


def email_form(F, E, ctx, lang):
    """No server: the form opens the buyer's email app with the request filled in (mailto), and shows the same text
    to copy when no email app opens. Requests land in order_email; you reply with a payment link."""
    f = lambda s: fmt(s, ctx)  # noqa: E731
    opts = "".join(f'<option value="{v}">{esc(t)}</option>' for v, t in F["rels"])
    errs = "".join(f'<p class="err" data-code="{k}" hidden>{f(F["errors"][k])}</p>' for k in ("domain", "email", "consent"))
    labels = json.dumps({"domain": F["domain"], "rel": F["rel"], "notes": F["notes"], "email": F["email"], "lang": lang})
    return f"""<form id="form" class="oform" data-to="{ctx["order_email"]}" data-subject="{esc(E["subject"])}" novalidate>{errs}
<label for="f-domain">{F["domain"]}</label><input id="f-domain" name="domain" required inputmode="url" autocomplete="off" placeholder="{F["domain_ph"]}" maxlength="120">
<label for="f-rel">{F["rel"]}</label><select id="f-rel" name="relationship" required>{opts}</select>
<label for="f-notes">{F["notes"]}</label><input id="f-notes" name="notes" maxlength="300" placeholder="{esc(F["notes_ph"])}">
<label for="f-email">{F["email"]}</label><input id="f-email" name="email" type="email" required autocomplete="email" maxlength="200">
<label class="chk" for="f-consent"><input id="f-consent" type="checkbox" name="consent" value="yes" required><span>{F["consent"]}</span></label>
<button class="btn big" type="submit">{E["submit"]} · {ctx["price"]}</button><p class="muted small">{f(E["after"])}</p>
<div id="fallback" class="fallback" hidden><p><b>{E["fallback_h"]}</b> {f(E["fallback_p"])}</p><textarea id="f-copy" rows="6" readonly></textarea></div></form>
<script>(function(){{var F=document.getElementById("form"),L={labels};
function err(c){{F.querySelectorAll(".err").forEach(function(e){{e.hidden=e.dataset.code!==c}});}}
F.addEventListener("submit",function(ev){{ev.preventDefault();
var d=F.domain.value.trim().toLowerCase().replace(/^https?:\/\//,"").replace(/^www\./,"").split(/[\/?#\s]/)[0];
if(!/^(?!-)(?:[a-z0-9-]{{1,63}}\.)+[a-z]{{2,24}}$/.test(d)){{err("domain");return;}}
if(!/^[^\s@<>]+@[^\s@<>]+\.[a-z]{{2,24}}$/i.test(F.email.value.trim())){{err("email");return;}}
if(!F.consent.checked){{err("consent");return;}} err("");
var r=F.relationship.options[F.relationship.selectedIndex].text;
var body=L.domain+": "+d+"\\n"+L.rel+": "+r+" ("+F.relationship.value+")\\n"+L.notes+": "+F.notes.value.trim()+"\\n"+L.email+": "+F.email.value.trim()+"\\nlang: "+L.lang+"\\nterms: accepted";
var subj=F.dataset.subject+": "+d;
document.getElementById("f-copy").value=subj+"\\n\\n"+body;document.getElementById("fallback").hidden=false;
location.href="mailto:"+F.dataset.to+"?subject="+encodeURIComponent(subj)+"&body="+encodeURIComponent(body);}});}})();</script>"""


def thanks(C, ctx, lang, prefix):
    T = C.THANKS
    return (head(C, lang, "thanks", T["title"], T["description"], prefix, noindex=True) + nav(C, lang, "thanks", prefix)
            + f'<main id="top"><section class="hero narrow"><h1>{T["h1"]}</h1>'
            + "".join(f'<p class="lede">{fmt(p, ctx)}</p>' for p in T["p"])
            + (f'<p class="lede">{fmt(T["p_details"], ctx)}</p>'
               if business(lang).get("checkout_fields") != "yes" and business(lang).get("order_mode") != "form" else "")
            + f'<p class="cta"><a class="btn ghost" href="index.html">{T["back"]}</a></p></section></main>' + foot(C, lang, "thanks", prefix))


def legal(C, ctx, lang, prefix, page, P):
    body = "".join(f'<section class="lg"><h2>{esc(h)}</h2><p>{fmt(t, ctx)}</p></section>' for h, t in P["sections"])
    return (head(C, lang, page, P["title"], P["description"], prefix) + nav(C, lang, page, prefix)
            + f'<main id="top" class="legal"><section class="hero narrow"><h1>{esc(P["title"])}</h1><p class="muted">{fmt(C.LEGAL_INTRO, ctx)}</p></section>'
            + body + "</main>" + foot(C, lang, page, prefix))


CSS = """
*{box-sizing:border-box}[hidden]{display:none!important}html{-webkit-text-size-adjust:100%;scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 var(--font-sans)}
a{color:inherit;text-underline-offset:2px}a:focus-visible,summary:focus-visible{outline:2px solid var(--ink);outline-offset:2px}
main,.nav,.foot{max-width:1120px;margin:0 auto;padding-left:max(24px,env(safe-area-inset-left,0px));padding-right:max(24px,env(safe-area-inset-right,0px))}
.nav{display:flex;justify-content:space-between;align-items:center;gap:16px;padding-top:18px;padding-bottom:18px}
.brand{display:flex;align-items:center;gap:10px;font-weight:700;font-size:17px;text-decoration:none}
.nav nav{display:flex;gap:18px;font-size:14px;align-items:center;flex-wrap:wrap;justify-content:flex-end}.nav nav a{text-decoration:none;color:var(--ink-2)}.nav nav a:hover{color:var(--ink)}
.nav .nav-order{color:var(--ink);font-weight:600}.nav .lang{border:1px solid var(--line);border-radius:999px;padding:2px 10px}
h1,h2,h3{margin:0;text-wrap:balance}h1{font:700 clamp(34px,5.4vw,58px)/1.08 var(--font-serif);letter-spacing:-.015em;max-width:18ch}
h2{font:700 30px/1.2 var(--font-serif);margin-bottom:10px}h3{font-size:16px;font-weight:600;margin:20px 0 10px}
p{margin:0;text-wrap:pretty}section{padding:56px 0;border-top:1px solid var(--line)}
.hero{border-top:0;padding:56px 0 64px}.hero.narrow{padding:48px 0 24px}.kicker{font:600 13px/1 var(--font-mono);color:var(--ink-2);margin-bottom:18px;text-transform:uppercase;letter-spacing:.04em}
.hl{color:inherit;background:linear-gradient(transparent 52%,var(--mark) 52%);-webkit-box-decoration-break:clone;box-decoration-break:clone}
.lede{font-size:19px;color:var(--ink-2);max-width:62ch;margin-top:22px}.small{font-size:13px}
.cta{display:flex;flex-wrap:wrap;gap:12px;margin-top:28px}
.btn{display:inline-block;padding:11px 18px;border-radius:var(--r-m);background:var(--ink);color:var(--bg);text-decoration:none;font-weight:600;font-size:15px}
.btn.ghost{background:transparent;color:var(--ink);box-shadow:inset 0 0 0 1.5px var(--ink)}.btn.big{font-size:17px;padding:14px 24px}
.btn.off{background:var(--surf);color:var(--ink-2);cursor:not-allowed}
.sub{color:var(--ink-2);max-width:70ch;margin-bottom:20px}.muted{color:var(--ink-2)}
mark.todo{background:var(--bad-bg);color:var(--bad);font:600 .85em/1.3 var(--font-mono);padding:0 4px;border-radius:4px}
.exs{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}.ex-date code{font:500 11px/1 var(--font-mono)}
.ex{border:1px solid var(--line);border-radius:var(--r-l);padding:20px;display:flex;flex-direction:column;gap:10px;min-width:0}
.ex h3{font:700 24px/1.2 var(--font-serif);margin:0}.ex-dom{font:500 12px/1 var(--font-mono);color:var(--ink-2)}
.ex-line{font-size:15px}.ex-n{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:4px 0 0}
.ex-n dt{font-size:12px;color:var(--ink-2)}.ex-n dd{margin:0;font-size:22px;font-weight:700;font-variant-numeric:tabular-nums}.ex-n small{font-size:12px;font-weight:500;color:var(--ink-2)}
.ex-gap{font-size:13px;color:var(--ink-2)}.ex-go{display:flex;flex-wrap:wrap;gap:8px;margin-top:auto;padding-top:6px}
.ex-go a{font-size:14px;font-weight:600;padding:7px 12px;border-radius:var(--r-s);background:var(--surf);text-decoration:none}.ex-go a:hover{background:var(--ink);color:var(--bg)}
.ex-date{font-size:12px;color:var(--ink-2)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:40px;align-items:start}
.dz{margin:0;padding-left:22px;display:grid;gap:6px}.plain{list-style:none;margin:0;padding:0;display:grid;gap:10px}.plain b{font-weight:600}
.dots li{padding-left:16px;position:relative}.dots li::before{content:"";position:absolute;left:0;top:.65em;width:6px;height:6px;border-radius:50%;background:var(--brand)}
.steps{list-style:none;counter-reset:s;margin:12px 0 0;padding:0;display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:16px}.steps.s3{grid-template-columns:repeat(3,minmax(0,1fr))}
.steps li{counter-increment:s;border-top:2px solid var(--ink);padding-top:12px;display:grid;gap:6px;align-content:start}
.steps li::before{content:counter(s,decimal-leading-zero);font:600 12px/1 var(--font-mono);color:var(--ink-2)}
.steps b{font-size:17px}.steps span{font-size:14px;color:var(--ink-2)}
.caught{margin-top:24px;border:1px solid var(--line);border-radius:var(--r-l);padding:20px 24px}.caught h3{margin-top:0}.caught .sub{margin-bottom:12px}.caught .plain+.sub{margin:12px 0 0}
.gate{margin-top:32px;background:var(--surf);border-radius:var(--r-l);padding:20px 24px}.gate h3{margin-top:0}
.codes{list-style:none;margin:0;padding:0;display:grid;gap:8px;font-size:15px}
.code{display:inline-block;width:26px;font:600 13px/1.6 var(--font-mono);text-align:center;border-radius:var(--r-s);background:var(--ink);color:var(--bg);margin-right:10px}
.tw{overflow-x:auto}table.grid{width:100%;border-collapse:collapse;font-size:14.5px}
.grid th,.grid td{text-align:left;vertical-align:top;padding:10px 14px 10px 0;border-top:1px solid var(--line)}
.grid thead th{font-size:12px;color:var(--ink-2);font-weight:600;border-top:0}.grid tbody th{font-weight:600;width:34%}.nw{white-space:nowrap}
.code-b{margin:0;background:var(--surf);border-radius:var(--r-m);padding:16px 18px;font:500 13px/1.6 var(--font-mono);overflow-x:auto;white-space:pre}
#run .code-b{margin:0 0 16px}
.band{display:flex;justify-content:space-between;align-items:center;gap:24px;flex-wrap:wrap}.band p{color:var(--ink-2);max-width:60ch}
.buy{margin-top:32px;border:1px solid var(--line);border-radius:var(--r-l);padding:24px;display:grid;gap:18px;max-width:760px}
.terms3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin:0}.terms3 dt{font-size:12px;color:var(--ink-2)}
.terms3 dd{margin:0;font-size:20px;font-weight:700}.terms3 small{display:block;font-size:12.5px;font-weight:400;color:var(--ink-2)}
.consent{font-size:13.5px;color:var(--ink-2);max-width:62ch}
.oform{display:grid;gap:8px;max-width:560px}.oform label{font-size:14px;font-weight:600;margin-top:8px}
.oform input,.oform select{font:16px/1.4 var(--font-sans);padding:10px 12px;border:1px solid var(--line);border-radius:var(--r-s);background:var(--bg);color:var(--ink);width:100%}
.oform input:focus,.oform select:focus{outline:2px solid var(--ink);outline-offset:1px}
.oform .chk{display:grid;grid-template-columns:auto 1fr;gap:10px;align-items:start;font-weight:400;font-size:13.5px;color:var(--ink-2);margin:10px 0}
.oform .chk input{width:18px;height:18px;margin-top:2px}.oform .btn{border:0;cursor:pointer;justify-self:start;margin-top:4px}
.fallback{margin-top:12px;display:grid;gap:8px}.fallback textarea{font:13px/1.5 var(--font-mono);padding:10px;border:1px solid var(--line);border-radius:var(--r-s);background:var(--surf);color:var(--ink);width:100%}
.hp{position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden}
.err{background:var(--bad-bg);color:var(--bad);border-radius:var(--r-s);padding:10px 12px;font-size:14px}
.faq{display:grid;gap:0;max-width:820px}.faq details{border-top:1px solid var(--line);padding:14px 0}.faq summary{cursor:pointer;font-weight:600}
.faq details p{margin-top:8px;color:var(--ink-2)}
.legal .lg{padding:24px 0;max-width:760px}.legal .lg h2{font-size:21px}.legal .lg p{color:var(--ink)}
.fine{font-size:14px;color:var(--ink-2)}.fine h2{font-size:20px;color:var(--ink)}
.foot{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;padding-top:24px;padding-bottom:40px;border-top:1px solid var(--line);font-size:14px}
.foot .fb{display:inline-flex;align-items:center;gap:8px;font-weight:700}.foot .logo{width:18px;height:18px}
@media (max-width:1060px){.exs{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:900px){.exs{grid-template-columns:1fr}.steps{grid-template-columns:1fr 1fr}.two{grid-template-columns:1fr;gap:24px}.terms3{grid-template-columns:1fr}}
@media (max-width:560px){main,.nav,.foot{padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
.nav nav a:not(.nav-order):not(.lang){display:none}.steps,.steps.s3{grid-template-columns:1fr}section{padding:40px 0}.lede{font-size:17px}.grid tbody th{width:auto}}
"""


HEADERS = """/*
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=()
/r/*
  X-Robots-Tag: noindex, nofollow, noarchive
  Referrer-Policy: no-referrer
  Cache-Control: private, no-store
/thanks.html
  X-Robots-Tag: noindex
/uk/thanks.html
  X-Robots-Tag: noindex
/fonts/*
  Cache-Control: public, max-age=31536000, immutable
"""  # Cloudflare Pages reads public/_headers


def main(domains):
    OUT.mkdir(exist_ok=True)
    for p in OUT.iterdir():  # keep delivered reports (public/r) between builds
        if p.name != "r":
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    (OUT / "examples").mkdir()
    exs = []
    for d in domains:
        src = ROOT / "output" / d
        if not (src / "index.html").exists():
            print(f"skip {d}: run build.py {d} first")
            continue
        shutil.copytree(src, OUT / "examples" / d)
        exs.append(example(d))
    for C in languages():
        lang = C.LANG
        base = OUT if lang == "en" else OUT / lang
        base.mkdir(exist_ok=True)
        prefix = "" if lang == "en" else "../"
        ctx = Ctx({**business(lang), "name": BR.NAME, "n_src": str(len(B.SOURCE_LABELS)), "home": "index.html"}, C.UI["todo"])
        pages = {"index": home(C, ctx, exs, lang, prefix), "order": order(C, ctx, lang, prefix), "thanks": thanks(C, ctx, lang, prefix),
                 "terms": legal(C, ctx, lang, prefix, "terms", C.TERMS), "privacy": legal(C, ctx, lang, prefix, "privacy", C.PRIVACY),
                 "refunds": legal(C, ctx, lang, prefix, "refunds", C.REFUNDS), "contact": legal(C, ctx, lang, prefix, "contact", C.CONTACT)}
        for name, html in pages.items():
            if "—" in re.sub(r"<style>.*?</style>", "", html, flags=re.S):
                sys.exit(f"em dash in {lang}/{name}.html")
            (base / f"{name}.html").write_text(html, encoding="utf-8")
        print(f"wrote {len(pages)} pages in {base} ({lang}), {len(exs)} examples")
    if (business("en").get("self_host_fonts") or "yes") == "yes":
        shutil.copytree(BR.FONT_DIR, OUT / "fonts")
        for f in OUT.rglob("*.html"):
            if "/r/" not in f.as_posix():
                f.write_text(BR.self_host_fonts(f.read_text(encoding="utf-8")), encoding="utf-8")
        print("fonts: self-hosted at /fonts/ (no Google request)")
    (OUT / "_headers").write_text(HEADERS, encoding="utf-8")
    (OUT / "robots.txt").write_text("User-agent: *\nDisallow: /r/\nDisallow: /thanks.html\nDisallow: /uk/thanks.html\n", encoding="utf-8")
    if MISSING:
        print("TO FILL in site/business.json: " + ", ".join(sorted(MISSING)))


if __name__ == "__main__":
    main(sys.argv[1:])
