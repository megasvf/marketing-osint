"""Collector 15 - blog: what the company publishes on its blog, how often, and what works.

1. Inventory: every blog-like URL (paths with /blog/, /resources/, /guides/, /academy/, /learn/, /hub/, /school/) from the sitemap files
   (re-read here, same crawler limits as sitemap.py); category / tag / author / pagination listings and non-English
   locale paths are excluded. Monthly counts for the last 12 months come from sitemap lastmod ("updated or published").
   When the sitemap has no usable lastmod, all blog pages (cap 350) are fetched and the page publish date is used.
   If the sitemap has no blog URLs at all, the /blog index pages are crawled instead.
2. Sample: the 40 most recent posts (by lastmod, else by publish date) are fetched; per post: title, H1, publish date,
   author (public byline name only), words, H2s, media, CTAs, product links, schema types, FAQ, tables, "vs" titles.
3. Each post gets a topic cluster and a funnel stage from the rule set in CLUSTER_RULES / stage() below (documented in note).
4. Traffic join: posts and blog URLs found in data/<domain>/ahrefs_organic.json top pages (mode: top 30 by traffic).

Product-link domains: the site itself, its subdomains, and aliases (--alias, e.g. a renamed sister domain).

Usage: python collectors/blog.py example.com [--alias example.org]
"""
import argparse
import copy
import json
import re
import statistics
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

import sitemap as sm
import threading
import time

from common import ROOT, SESSION, _geo_locale_redirected, clean, fetch, write_source

LOCK = threading.Lock()

SAMPLE = 40
SPARE = 14            # extra candidates fetched so failures do not shrink the sample
STOP_RUN = 20         # ordered mode: stop after this many consecutive posts older than the 12-month window
PROBE_CAP = 1200      # max pages fetched to recover publish dates when the sitemap lastmod is missing or bulk-stamped
MIN_WORDS = 120       # shorter pages are hubs / landing pages, not articles
TODAY = date.today()
NO_DASH = str.maketrans({"—": "-", "–": "-", " ": " "})

BLOG_SEG = {"blog", "resources", "guides", "academy", "learn", "hub", "school"}  # hub: content hubs (example.com/hub/...)
LISTING_SEG = {"category", "categories", "tag", "tags", "author", "authors", "page", "topic", "topics", "archive",
               "archives", "feed", "search", "label"}
LOCALE_RX = re.compile(r"^[a-z]{2}(?:-[a-z]{2,4})?$", re.I)
ENGLISH = {"en", "en-us", "en-gb", "en-ca", "en-au"}


def tidy(s, limit=None):
    return clean((s or "").translate(NO_DASH), limit)


# ------------------------------------------------------------------ inventory

def blog_kind(url):
    """Return ('post'|'listing'|None, locale). A post is a blog-like URL with a slug below the section."""
    p = urlparse(url)
    segs = [s for s in p.path.lower().split("/") if s]
    locale = None
    if segs and LOCALE_RX.match(segs[0]) and segs[0] not in BLOG_SEG and len(segs) > 1 and segs[1] in BLOG_SEG:
        locale, segs = segs[0], segs[1:]
    if not segs or not (set(segs) & BLOG_SEG):
        return None, locale
    i = next(k for k, s in enumerate(segs) if s in BLOG_SEG)
    rest = segs[i + 1:]
    if not rest or set(rest) & LISTING_SEG or re.fullmatch(r"\d+", rest[-1]) or p.query:
        return "listing", locale
    return "post", locale


def get_xml(url):
    """sitemap.get_bytes with up to 3 tries (sitemap hosts sometimes time out under parallel reads)."""
    for k in range(3):
        txt = sm.get_bytes(url)
        if txt:
            return txt
        time.sleep(2 * (k + 1))
    return None


def collect_sitemap_urls(domain):
    roots, via = sm.find_roots(domain)
    urls, failed, queue, children, seen = {}, [], [(r, 0) for r in roots], 0, set()
    while queue:
        batch, queue = queue, []
        todo = []
        for s, depth in batch:
            if s in seen:
                continue
            seen.add(s)
            if depth > 0:
                if children >= sm.MAX_CHILD:
                    continue
                children += 1
            todo.append((s, depth))
        with ThreadPoolExecutor(4) as ex:
            texts = list(ex.map(lambda t: get_xml(t[0]), todo))
        for (s, depth), xml in zip(todo, texts):
            if not xml:
                failed.append(s)
                continue
            kind, rows = sm.parse(xml)
            if kind == "index" and depth < 2:
                queue += [(loc, depth + 1) for loc, _ in rows]
            else:
                for loc, lm in rows:
                    urls.setdefault(loc, (lm, s))
    return urls, roots, via, len(seen), failed


def index_crawl(domain):
    """Fallback inventory: links to posts found on /blog index pages (?page=N), newest first as listed."""
    found, notes = {}, []
    for root in ("blog", "resources", "guides", "academy", "learn"):
        for pg in range(1, 8):
            u = f"https://{domain}/{root}" + ("" if pg == 1 else f"?page={pg}")
            fu, html = fetch(u)
            if not html:
                break
            new = 0
            for a in BeautifulSoup(html, "lxml").find_all("a", href=True):
                h = urljoin(fu, a["href"]).split("#")[0].split("?")[0]
                if urlparse(h).netloc.replace("www.", "") == domain.replace("www.", "") and blog_kind(h)[0] == "post" \
                        and h not in found:
                    found[h] = (None, fu)
                    new += 1
            if not new:
                break
        if found:
            notes.append(f"index pages of /{root}")
            break
    return found, notes


# ------------------------------------------------------------------ date + schema helpers

DATE_FORMATS = ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%d %B %Y", "%d %b %Y", "%b %d %Y", "%B %d %Y")


def parse_date(val):
    if not val:
        return None
    v = clean(str(val))
    m = re.match(r"(20\d\d)-(\d\d)-(\d\d)", v)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    v = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", v.replace(".", ""))
    for f in DATE_FORMATS[1:]:
        try:
            return datetime.strptime(v, f).date()
        except ValueError:
            pass
    return None


def ld_nodes(soup):
    out = []

    def walk(n):
        if isinstance(n, list):
            for x in n:
                walk(x)
        elif isinstance(n, dict):
            out.append(n)
            for k in ("@graph", "mainEntity", "itemListElement"):
                if k in n:
                    walk(n[k])

    for s in soup.find_all("script", type=re.compile("ld\\+json", re.I)):
        raw = (s.string or s.get_text() or "").strip()
        try:
            walk(json.loads(raw))
        except Exception:
            try:
                walk(json.loads(re.sub(r"[\x00-\x1f]+", " ", raw)))
            except Exception:
                continue
    return out


def node_types(n):
    t = n.get("@type")
    return [t] if isinstance(t, str) else [x for x in (t or []) if isinstance(x, str)]


PLACEHOLDER = re.compile(r"placeholder|^author$|^undefined$|^null$|lorem", re.I)
GENERIC_AUTHOR = re.compile(r"^(team|staff|admin|editor(ial)?( team)?|guest|marketing( team)?|the .* team)$", re.I)


def extract_author(soup, nodes, brand):
    """Public byline name only; returns (name_or_None, role_or_note)."""
    cand = None
    for n in nodes:
        a = n.get("author")
        if not a:
            continue
        for x in (a if isinstance(a, list) else [a]):
            if isinstance(x, dict):
                nm, typ = x.get("name"), node_types(x)
                if nm and "Organization" not in typ:
                    if PLACEHOLDER.search(nm):
                        continue  # CMS template default, not a real byline
                    cand = tidy(nm, 60)
                    break
                if nm and "Organization" in typ:
                    return None, "brand/organization byline"
            elif isinstance(x, str):
                cand = tidy(x, 60)
                break
        if cand:
            break
    if not cand:
        m = soup.find("meta", attrs={"name": "author"}) or soup.find("meta", attrs={"property": "article:author"})
        if m and m.get("content") and not m["content"].startswith("http"):
            cand = tidy(m["content"], 60)
    if not cand:
        for e in soup.find_all(class_=re.compile(r"author[-_]?(name|text|link)|byline|post-author", re.I)):
            t = tidy(re.sub(r"^\s*(written\s+)?by\s*:?\s*", "", e.get_text(" "), flags=re.I), 80)
            if 2 <= len(t) <= 40 and not re.search(r"\d|logout|login", t, re.I):
                cand = t
                break
    if not cand:
        return None, "no byline found"
    if GENERIC_AUTHOR.match(cand) or cand.lower().replace(" ", "") == brand:
        return None, "brand/team byline"
    return cand, "named byline"


# ------------------------------------------------------------------ per-post extraction

CONTAINER_SEL = ["article", "[class*=blog-post-content_comp]", "[class*=post-content]", "[class*=article-content]",
                 "[class*=entry-content]", "[class*=rich-text]", "[class*=richtext]", "main"]
VIDEO_HOST = re.compile(r"youtube\.com|youtu\.be|youtube-nocookie|vimeo\.com|wistia|loom\.com|vidyard|brightcove|player\.", re.I)
SIGNUP_TXT = re.compile(r"sign ?up|get started|start (for )?free|try (it |\w+ )?(for )?(free|now)|create (a |an |your )?(free )?account|"
                        r"start (building|designing|creating)|book (a )?demo|request (a )?demo|see pricing|view pricing|"
                        r"use (this )?template|browse templates|get (the )?template|download (the )?template|try .{0,25}(free|demo)", re.I)

CLUSTER_RULES = [  # first matching rule wins; pass 1 on title + slug, pass 2 on the first 8 H2s
    ("comparison / alternatives", r"\bvs\.?\b|versus|alternatives?\b|compar(e|ison|ing)|\bbest .{0,40}(builders?|software|tools?|platforms?|providers?|services?|editors?|esps?|apps?)\b"),
    ("case study / customer", r"case[- ]stud|customer stor|success stor|\bhow .{0,40}(increased|grew|boosted|doubled|tripled|saved|achieved)\b|\bcustomer spotlight|\bstory of\b"),
    ("product update / release", r"\bintroducing\b|\bannounc|\brelease\b|\bnew feature|what'?s new|\bnow available\b|\bproduct update|\blaunch(es|ed|ing)?\b|"
                                 r"\brebrand|\bis now\b|\bletter from\b|\bnew integration|\bupdates? (to|for|in)\b|\bis here\b|\bmeet (the )?new\b"),
    ("holidays & seasonal", r"black friday|cyber monday|christmas|holiday|halloween|valentine|easter|thanksgiving|mother'?s day|father'?s day|new year|"
                            r"back[- ]to[- ]school|\b(summer|spring|fall|autumn|winter)\b|seasonal|ramadan|diwali|st\.? patrick|independence day|labor day|"
                            r"singles'? day|lunar|\beid\b|memorial day|earth day|pride month|women'?s day"),
    ("AI", r"\bai\b|\ba\.i\.|artificial intelligence|chatgpt|\bgpt\b|\bllms?\b|generative|copilot|machine learning|agentic|\bmcp\b|\bclaude\b|\bgemini\b"),
    ("engineering & developers", r"\bapi\b|\bsdks?\b|developer|engineering|\bcode\b|open[- ]source|github|security|privacy|infrastructure|"
                                 r"performance|latency|database|\bbackend\b|\bfrontend\b|\bplugins?\b|webhooks?|\bdevops\b|architecture"),
    ("measurement & optimization", r"a/b test|\bab test|split test|experiment|conversion|\bcro\b|analytics|attribution|\bmetrics\b|\bkpis?\b|dashboards?|"
                                   r"reporting|benchmark|open rates?|click[- ]through|\bctr\b|deliverab|spam|inbox placement|dmarc|\bspf\b|dkim|"
                                   r"bounce|preview|rendering|email clients?|compliance|gdpr|can-spam|accessib"),
    ("templates & inspiration", r"templates?|examples?|inspir|\bideas\b|gallery|swipe|showcase|lookbook|\bbest .{0,25}(designs?|emails?|websites?|pages?)\b"),
    ("design & creativity", r"dark mode|design trends?|typography|colou?rs?\b|\bfonts?\b|responsive|mobile|layout|\bux\b|\bui\b|visual|illustrat|"
                            r"\bimages?\b|photo|video editing|\bgifs?\b|\bhtml\b|\bcss\b|branding|logo|prototyp|wirefram|\bdesign\b|creativ"),
    ("productivity & collaboration", r"productiv|collaborat|teamwork|\bteams?\b|remote|hybrid work|meetings?|project management|\btasks?\b|"
                                     r"\bwikis?\b|knowledge base|documentation|\bnotes?\b|organi[sz]|workflow|planning|roadmap|okrs?\b|focus|habits?"),
    ("company & culture", r"\bculture\b|\bhiring\b|careers?|we'?re hiring|our team|\bvalues\b|diversity|inclusion|\bfounders?\b|funding|"
                          r"series [a-f]\b|acquisition|\bipo\b|anniversary|\bmission\b"),
    ("how-to / tutorial", r"\bhow (to|do|can|does)\b|guide to|step[- ]by[- ]step|tutorial|\btips\b|\bways to\b|checklist|\bwhat is\b|\bwhat are\b|"
                          r"best practices|\bsteps\b|cheat sheet|walkthrough|beginner|\bbasics\b|\bwhy\b"),
    ("marketing & growth", r"strateg|campaign|segment|automation|\bflows?\b|subject lines?|newsletter|marketing|engagement|retention|"
                           r"lifecycle|onboarding|welcome|abandon|cart|e-?commerce|\bb2b\b|\bb2c\b|\bsales\b|\broi\b|personali|trends?|"
                           r"list[- ]building|\blead|subscribers?|audience|\bbrand\b|content|growth|copywriting|\bcrm\b|\bseo\b|social media|"
                           r"transactional|drip|\bsms\b|\bads?\b|advertis"),
]
CLUSTER_RX = [(n, re.compile(rx, re.I)) for n, rx in CLUSTER_RULES]
TOFU_TITLE = re.compile(r"^(what is|what are|why|the (history|state|future|rise)|\d+ (stats|statistics)|email marketing statistics|glossary|definition)\b|"
                        r"\bstatistics\b|\bglossary\b|\btrends?\b|\bideas\b|\binspiration\b|\bexamples?\b|\bhistory of\b", re.I)
BOFU_TITLE = re.compile(r"\bpricing\b|\bdemo\b|free trial|switch(ing)? (from|to)|migrat|\bvs\.?\b|versus|alternatives?\b|\breview\b|\bplans?\b", re.I)


def classify_cluster(title, slug, h2s):
    for text in (f"{title} {slug.replace('-', ' ')}", " ".join(h2s[:8])):
        for name, rx in CLUSTER_RX:
            if rx.search(text):
                return name
    return "other"


def stage(cluster, title, brand_rx, product_ctas):
    """TOFU / MOFU / BOFU. Rules, in order:
    BOFU: comparison or case study cluster; or title has pricing/demo/trial/switch/migrate/vs/alternatives/review;
          or the brand/product name is in a how-to / templates / design title (product-led tutorial) ;
    TOFU: title is definitional (what is / why / statistics / trends / ideas / examples / history), or cluster is
          holidays & seasonal / other / templates & inspiration;
    MOFU: everything else (how-to, marketing, measurement, engineering, productivity, culture, AI, design, product update)."""
    if cluster in ("comparison / alternatives", "case study / customer") or BOFU_TITLE.search(title):
        return "BOFU"
    if brand_rx.search(title) and cluster in ("how-to / tutorial", "templates & inspiration", "design & creativity",
                                               "measurement & optimization", "productivity & collaboration", "AI"):
        return "BOFU"
    if TOFU_TITLE.search(title) or cluster in ("holidays & seasonal", "other", "templates & inspiration"):
        return "TOFU"
    return "MOFU"


def norm_host(h):
    return h.lower().replace("www.", "")


def in_family(host, family):
    host = norm_host(host)
    return any(host == f or host.endswith("." + f) for f in family)


def link_category(path, host, family_root_hosts):
    p = path.lower()
    h = norm_host(host)
    if re.search(r"/pricing|pricing-plans|/plans\b", p):
        return "pricing"
    if re.search(r"/book-a-demo|/demo\b|/studio/demo|request-a-demo", p) or re.search(r"/demo", p):
        return "demo"
    if re.search(r"/sign-?up|/register|/get-started|/app/|/auth(?:/|$)|/login", p) or h.startswith("app.") or h.startswith("my."):
        return "signup"
    if re.search(r"/templates?(/|$)|template-gallery|/email-templates", p):
        return "templates"
    if re.search(r"/plugin|/sdk|/api\b|/developers?|/embed", p) or h.startswith("developers."):
        return "plugin_sdk"
    if re.search(r"/features?(/|$)|/email-(editor|builder)|/builder|/studio|/landing-page-builder|/editor|/ai-|/amp|/integrations?(/|$)", p):
        return "features"
    return None


def extract_post(url, html, family, brand, brand_rx):
    soup = BeautifulSoup(html, "lxml")
    nodes = ld_nodes(soup)
    schema = sorted({t for n in nodes for t in node_types(n) if t not in ("ListItem", "ImageObject", "Organization", "WebSite", "WebPage", "SiteNavigationElement", "Person", "BreadcrumbList", "Question", "Answer", "HowToStep", "HowToSection", "EntryPoint", "SearchAction", "ReadAction", "Thing")}
                    | ({"BreadcrumbList"} if any("BreadcrumbList" in node_types(n) for n in nodes) else set()))
    # publish date
    pub = None
    for key in ("article:published_time", "og:article:published_time", "publication-date", "datePublished", "date", "pubdate"):
        m = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
        if m and parse_date(m.get("content")):
            pub = parse_date(m["content"])
            break
    if not pub:
        for n in nodes:
            if parse_date(n.get("datePublished")):
                pub = parse_date(n["datePublished"])
                break
    if not pub:
        t = soup.find("time", attrs={"datetime": True})
        pub = parse_date(t["datetime"]) if t else None
    if not pub:
        m = re.search(r'"datePublished"\s*:\s*"(20\d\d-\d\d-\d\d)', html)
        pub = parse_date(m.group(1)) if m else None
    modified = None
    m = soup.find("meta", attrs={"property": "article:modified_time"})
    if m:
        modified = parse_date(m.get("content"))
    if not modified:
        for n in nodes:
            if parse_date(n.get("dateModified")):
                modified = parse_date(n["dateModified"])
                break
    author, author_note = extract_author(soup, nodes, brand)
    title = tidy(soup.title.get_text(), 200) if soup.title else ""
    h1s = [tidy(x.get_text(" "), 200) for x in soup.find_all("h1")]
    for t in soup(["script", "style", "noscript", "svg"]):
        t.decompose()
    cont = None
    for sel in CONTAINER_SEL:
        els = [e for e in soup.select(sel) if len(e.get_text(" ").split()) > 150]
        if els:
            cont = max(els, key=lambda e: len(e.get_text(" ")))
            break
    cont = cont or soup.body or soup
    body = copy.copy(cont)
    for t in body.select("aside, nav, form, footer, header, [class*=comment], [class*=related], [class*=newsletter], [class*=subscribe], [class*=share], [class*=sidebar]"):
        t.decompose()
    words = len(body.get_text(" ").split())
    h2s = [tidy(h.get_text(" "), 140) for h in cont.find_all("h2") if tidy(h.get_text(" "))]
    h2s = [h for h in h2s if not re.fullmatch(r"(related( posts| articles)?|comments?|leave a (reply|comment)|share|subscribe.*|table of contents|contents?)", h, re.I)]
    imgs = set()
    for im in cont.find_all("img"):
        src = im.get("data-src") or im.get("src") or (im.get("srcset") or "").split(" ")[0]
        cls = " ".join(im.get("class", [])).lower()
        if not src or src.startswith("data:image/svg") or re.search(r"avatar|icon|logo|emoji|author|sprite|pixel", cls + " " + src.lower()):
            continue
        imgs.add(src)
    video, interactive = 0, 0
    for f in cont.find_all("iframe"):
        src = f.get("src") or f.get("data-src") or ""
        if VIDEO_HOST.search(src):
            video += 1
        elif src:
            interactive += 1
    video += len(cont.find_all("video"))
    interactive += len([e for e in cont.find_all(True) if e.name.startswith("amp-")])
    # CTAs and product links (in the article body only: header / footer / mega-menu excluded)
    ctas, cats, cat_urls = [], Counter(), {}
    scan = copy.copy(cont)
    for t in scan.select("nav, header, footer, aside, [class*=navbar], [class*=mega], [class*=menu]"):
        t.decompose()
    for a in scan.find_all(["a", "button"]):
        txt = tidy(a.get_text(" "), 60)
        href = a.get("href") if a.name == "a" else None
        absu, host, kind = None, "", None
        if href and not href.startswith(("#", "mailto:", "javascript:", "tel:")):
            absu = urljoin(url, href)
            host = urlparse(absu).netloc
            if in_family(host, family):
                kind = link_category(urlparse(absu).path, host, family)
                if kind and absu.split("#")[0].rstrip("/") not in cat_urls.setdefault(kind, set()):
                    cat_urls[kind].add(absu.split("#")[0].rstrip("/"))
                    cats[kind] += 1
        is_cta = bool(txt) and bool(SIGNUP_TXT.search(txt)) and (a.name == "button" or (absu and in_family(host, family)))
        if not is_cta and kind in ("signup", "demo") and txt:
            is_cta = True
        if is_cta and txt not in ctas:
            ctas.append(txt)
    faq = ("FAQPage" in schema) or bool(re.search(r"\bfaq\b|frequently asked", " ".join(h2s), re.I)) or bool(cont.find("details"))
    tables = len(cont.find_all("table"))
    slug = urlparse(url).path.rstrip("/").split("/")[-1]
    ttl = h1s[0] if h1s else re.sub(r"\s*[|\-]\s*[^|\-]{2,30}$", "", title)
    cluster = classify_cluster(ttl, slug, h2s)
    return {
        "title": ttl or title, "html_title": title, "h1": h1s[0] if h1s else "", "date": pub, "modified": modified,
        "author": author, "author_note": author_note, "words": words, "h2": len(h2s), "h2_list": h2s[:8],
        "images": len(imgs), "video": video, "interactive": interactive,
        "ctas": ctas[:6], "ctas_n": len(ctas), "product_links": dict(cats), "product_links_n": sum(cats.values()),
        "schema": schema, "faq": faq, "tables": tables,
        "vs_title": bool(re.search(r"\bvs\.?\b|versus|alternatives?\b", ttl + " " + slug.replace("-", " "), re.I)),
        "comparison_table": bool(tables and re.search(r"\bvs\.?\b|versus|alternativ|compar", ttl + " " + " ".join(h2s), re.I)),
        "cluster": cluster, "stage": stage(cluster, ttl, brand_rx, len(ctas)),
    }


# ------------------------------------------------------------------ traffic join

def norm_url(u):
    p = urlparse(u)
    return (norm_host(p.netloc) + p.path.rstrip("/")).lower()


def load_ahrefs(domain):
    f = ROOT / "data" / domain / "ahrefs_organic.json"
    if not f.exists():
        return {}, "ahrefs_organic.json missing"
    j = json.loads(f.read_text(encoding="utf-8"))
    out = {}
    for i in j.get("items", []):
        tr = (i.get("meta") or {}).get("sum_traffic")
        if i.get("type") == "page" and tr is not None and i.get("url"):
            key = norm_url(i["url"])
            if key in out:  # www and non-www (or slash variants) collapse to one key: sum, never overwrite
                out[key]["traffic"] += tr
                continue
            out[key] = {"traffic": tr, "url": i["url"], "keyword": (i.get("meta") or {}).get("top_keyword"),
                        "keywords": (i.get("meta") or {}).get("keywords")}
    return out, f"{len(out)} top pages in ahrefs_organic.json (www and non-www merged by summing)"


def month_list():
    out, y, m = [], TODAY.year, TODAY.month
    for _ in range(12):
        out.append(f"{y}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[::-1]


def share(n, d):
    return round(100 * n / d, 1) if d else 0.0


# ------------------------------------------------------------------ polite fetching

_WARMED = {}
_LAST = [0.0]
MIN_GAP = 0.45   # seconds between requests across all threads (some sites answer 429 above ~3 req/s)


def throttle():
    with LOCK:
        wait = _LAST[0] + MIN_GAP - time.time()
        if wait > 0:
            time.sleep(wait)
        _LAST[0] = time.time()


def get_page(u):
    """GET with throttle, 429/5xx backoff and the English-locale cookie fix. Returns (final_url, html or None, tag)."""
    html, fu = None, u
    for k in range(5):
        throttle()
        try:
            r = SESSION.get(u, timeout=25, allow_redirects=True)
        except Exception:
            time.sleep(2 * (k + 1))
            continue
        fu = r.url
        if r.status_code == 429 or r.status_code >= 500:
            try:
                wait = min(60, int(r.headers.get("Retry-After", "")))
            except ValueError:
                wait = 6 * (k + 1)
            time.sleep(wait)
            continue
        if r.status_code >= 400 or "html" not in r.headers.get("content-type", ""):
            return fu, None, "http"
        if not r.encoding or r.encoding.lower() == "iso-8859-1":
            r.encoding = "utf-8"
        if _geo_locale_redirected(u, fu):
            host = urlparse(u).netloc
            with LOCK:
                fresh = host not in _WARMED
                _WARMED[host] = True
            if fresh:
                p = urlparse(u)
                throttle()
                SESSION.get(f"{p.scheme}://{host}/en{p.path}", timeout=25)
                continue
            return fu, None, "locale"
        html = r.text
        break
    return fu, html, ("ok" if html else "failed")


def index_extras(family, posts):
    """Add post links found on each family host's blog index (first page + ?*page=N pagination, max 12 pages)."""
    added = 0
    for host in family:
        mine = [u for u in posts if norm_host(urlparse(u).netloc) == host]
        if not mine:
            continue
        pref = Counter(re.match(r"(.*?/(?:%s))(?:/|$)" % "|".join(sorted(BLOG_SEG)), urlparse(u).path.lower()).group(1)
                       for u in mine if re.match(r"(.*?/(?:%s))(?:/|$)" % "|".join(sorted(BLOG_SEG)), urlparse(u).path.lower()))
        if not pref:
            continue
        url, seen_pages = f"https://{host}{pref.most_common(1)[0][0]}", set()
        for _ in range(12):
            if url in seen_pages:
                break
            seen_pages.add(url)
            fu, html, tag = get_page(url)
            if not html:
                break
            soup = BeautifulSoup(html, "lxml")
            for a in soup.find_all("a", href=True):
                h = urljoin(fu, a["href"]).split("#")[0].split("?")[0]
                if blog_kind(h)[0] == "post" and in_family(urlparse(h).netloc, family) and not (blog_kind(h)[1] and blog_kind(h)[1] not in ENGLISH):
                    if h not in posts and h.rstrip("/") not in posts and h.rstrip("/") + "/" not in posts:
                        posts[h] = (None, fu)
                        added += 1
            nxt = [urljoin(fu, a["href"]) for a in soup.find_all("a", href=True)
                   if re.search(r"[?&][\w]*page=\d+", a["href"]) and urljoin(fu, a["href"]) not in seen_pages]
            if not nxt:
                break
            url = nxt[0]
    return added


def index_order(domain, posts):
    """Post URLs in blog index order (?page=N), newest first as the site lists them. Empty when there is no pagination."""
    out, seen = [], set()
    for root in ("blog", "resources", "guides", "academy", "learn"):
        for pg in range(1, 80):
            u = f"https://{domain}/{root}/" + ("" if pg == 1 else f"?page={pg}")
            fu, html, tag = get_page(u)
            if not html:
                break
            new = 0
            for a in BeautifulSoup(html, "lxml").find_all("a", href=True):
                h = urljoin(fu, a["href"]).split("#")[0].split("?")[0]
                for cand in (h, h.rstrip("/") + "/", h.rstrip("/")):
                    if cand in posts and cand not in seen:
                        seen.add(cand)
                        out.append(cand)
                        new += 1
                        break
            if not new:
                break
        if out:
            break
    return out


# ------------------------------------------------------------------ main

def main(domain, aliases):
    brand = domain.split(".")[0].lower()
    family = [norm_host(domain)] + [norm_host(a) for a in (aliases or [])]
    brand_rx = re.compile(r"\b(" + "|".join(re.escape(x.split(".")[0]) for x in family) + r")\b", re.I)
    notes = []
    urls, roots, via, nfiles, failed = collect_sitemap_urls(domain)
    posts, skipped_locale, listings = {}, 0, 0
    for u, (lm, src) in urls.items():
        kind, loc = blog_kind(u)
        if kind == "listing":
            listings += 1
        elif kind == "post":
            if loc and loc.lower() not in ENGLISH:
                skipped_locale += 1
                continue
            if urlparse(u).netloc.replace("www.", "") != domain.replace("www.", "") and not in_family(urlparse(u).netloc, family):
                continue
            posts[u] = (lm if lm and re.match(r"\d{4}-\d{2}-\d{2}$", lm) else None, src)
    source_desc = f"sitemap ({nfiles} files read via {via})"
    for alias in family[1:]:
        a_urls, a_roots, a_via, a_n, a_failed = collect_sitemap_urls(alias)
        added = 0
        for u, (lm, src) in a_urls.items():
            kind, loc = blog_kind(u)
            if kind == "post" and not (loc and loc.lower() not in ENGLISH) and in_family(urlparse(u).netloc, family) and u not in posts:
                posts[u] = (lm if lm and re.match(r"\d{4}-\d{2}-\d{2}$", lm) else None, src)
                added += 1
        if added:
            notes.append(f"{added} blog URLs added from alias domain {alias} (content migrated there; {alias} sitemap lastmod not trusted)")
    extras = index_extras(family, posts)
    if extras:
        notes.append(f"{extras} post URLs found only on blog index pages (missing from sitemaps)")
    if not posts:
        posts, n2 = index_crawl(domain)
        source_desc = "blog index pages (" + ", ".join(n2) + ")" if n2 else "none"
        notes.append("no blog URLs in the sitemap; inventory comes from index pages, so counts are a lower bound")
    if not posts:
        return write_source(domain, "blog", "unavailable", [], f"no blog URLs found in sitemap ({len(urls)} URLs) or on index pages")
    notes.append(f"inventory: {len(posts)} English blog-like post URLs ({listings} listing URLs and {skipped_locale} non-English locale posts excluded)")

    lm_dates = {u: parse_date(lm) for u, (lm, _) in posts.items() if lm}
    distinct = len(set(lm_dates.values()))
    stamp, stamp_n = None, 0
    if lm_dates:
        stamp, stamp_n = Counter(lm_dates.values()).most_common(1)[0]
        if stamp_n <= 0.25 * len(lm_dates):
            stamp = None
    has_lastmod = len(lm_dates) >= 0.5 * len(posts) and distinct > 3 and stamp is None
    if stamp:
        notes.append(f"sitemap lastmod is bulk-stamped ({stamp_n} of {len(lm_dates)} URLs share {stamp}), so lastmod is not used for monthly counts or ordering")
    elif not lm_dates:
        notes.append("sitemap has no lastmod values")
    def process(u):
        """Fetch one post (English only) and extract its record: (final_url, record), ('LOCALE'|'ERR', info) or None."""
        try:
            fu, html, tag = get_page(u)
            if tag == "locale":
                return ("LOCALE", u)
            if not html:
                return None
            return fu, extract_post(fu, html, family, brand, brand_rx)
        except Exception as e:
            return ("ERR", f"{u}: {type(e).__name__}")

    months = month_list()
    cutoff12 = date(int(months[0][:4]), int(months[0][5:]), 1)
    ordered_mode = False
    if has_lastmod:
        basis = "sitemap lastmod (updated or published)"
        ordered = sorted(posts, key=lambda u: lm_dates.get(u) or date.min, reverse=True)
        cand = ordered[:SAMPLE + SPARE]
        date_for_month = dict(lm_dates)
    else:
        listing = index_order(domain, posts)
        covered = [u for u in listing if u in posts]
        ordered_mode = len(covered) >= 0.6 * len(posts)
        if ordered_mode:
            seen_c = set(covered)
            cand = covered + [u for u in posts if u not in seen_c]
            basis = ("page publish date (no usable sitemap lastmod; posts fetched newest-first in blog index order until "
                     f"{STOP_RUN} consecutive posts predate the 12-month window)")
            notes.append(f"blog index order covers {len(covered)} of {len(posts)} post URLs")
        else:
            cand = list(posts)[:PROBE_CAP]
            basis = "page publish date (no usable sitemap lastmod; every blog page fetched, cap %d)" % PROBE_CAP
            if len(posts) > PROBE_CAP:
                notes.append(f"{len(posts) - PROBE_CAP} blog URLs beyond the {PROBE_CAP} fetch cap not dated, monthly counts are a lower bound")
    parsed, locale_dropped, errs, unfetched, tried = {}, 0, [], 0, 0
    batch, older_run, i = 24, 0, 0
    seen_final, dup_skipped = set(), 0
    while i < len(cand):
        chunk = [u for u in cand[i:i + batch] if norm_url(u) not in seen_final]
        dup_skipped += len(cand[i:i + batch]) - len(chunk)
        i += batch
        with ThreadPoolExecutor(3) as ex:
            results = list(ex.map(process, chunk))
        for u, res in zip(chunk, results):
            tried += 1
            if res is None:
                unfetched += 1
            elif res[0] == "LOCALE":
                locale_dropped += 1
            elif res[0] == "ERR":
                errs.append(res[1])
            else:
                if norm_url(res[0]) in seen_final:
                    dup_skipped += 1  # two sitemap URLs redirect to the same page
                    continue
                seen_final.add(norm_url(res[0]))
                seen_final.add(norm_url(u))
                parsed[u] = res
                d = res[1]["date"]
                if d:
                    older_run = older_run + 1 if d < cutoff12 else 0
        if ordered_mode and older_run >= STOP_RUN and len(parsed) >= SAMPLE:
            break
    stopped_early = i < len(cand)
    if dup_skipped:
        notes.append(f"{dup_skipped} URLs skipped as duplicates (redirect to a page already collected)")
    if ordered_mode:
        dts = [parsed[u][1]["date"] for u in cand if u in parsed and parsed[u][1]["date"]]
        mono = round(100 * sum(1 for x, y in zip(dts, dts[1:]) if x >= y) / max(1, len(dts) - 1))
        notes.append(f"fetched {len(parsed)} newest-first posts; index order matches publish-date order for {mono}% of adjacent pairs"
                     + (f"; {len(cand) - tried} older posts never fetched (assumed older than 12 months)" if stopped_early else ""))
        if unfetched:
            notes.append(f"{unfetched} of {tried} requested pages failed after retries (rate limit or HTTP error)")
    else:
        notes.append(f"{len(parsed)} of {tried} candidate pages fetched and parsed"
                     + (f" ({unfetched} failed after retries, counts are a lower bound)" if unfetched else ""))
    if locale_dropped:
        notes.append(f"{locale_dropped} pages dropped: server redirected to a non-English locale")
    if errs:
        notes.append(f"{len(errs)} parse errors, e.g. {errs[0]}")
    if not has_lastmod:
        date_for_month = {u: r["date"] for u, (_, r) in parsed.items() if r["date"]}
        undated = len(parsed) - len(date_for_month)
        if undated:
            notes.append(f"{undated} fetched pages had no readable publish date")
    articles = {u: v for u, v in parsed.items() if v[1]["words"] >= MIN_WORDS}
    thin = len(parsed) - len(articles)
    if thin:
        notes.append(f"{thin} fetched pages under {MIN_WORDS} words (hub / landing pages) left out of the sample")
    if has_lastmod:
        sample_urls = [u for u in ordered if u in articles][:SAMPLE]
    else:
        sample_urls = sorted(articles, key=lambda u: (articles[u][1]["date"] or date.min), reverse=True)[:SAMPLE]
    if len(sample_urls) < SAMPLE:
        notes.append(f"only {len(sample_urls)} posts could be parsed (target {SAMPLE})")

    by_month = {k: 0 for k in months}
    for u, d in date_for_month.items():
        if d:
            k = d.strftime("%Y-%m")
            if k in by_month:
                by_month[k] += 1
    pub_by_month = {k: 0 for k in months}
    for u in sample_urls:
        d = parsed[u][1]["date"]
        if d and d.strftime("%Y-%m") in pub_by_month:
            pub_by_month[d.strftime("%Y-%m")] += 1

    ahr, ahr_note = load_ahrefs(domain)
    notes.append(ahr_note)
    recs = [(u, parsed[u][0], parsed[u][1]) for u in sample_urls]
    for u, fu, r in recs:
        hit = ahr.get(norm_url(fu)) or ahr.get(norm_url(u))
        r["ahrefs_traffic"] = hit["traffic"] if hit else None

    items = []
    blog_root = f"https://{domain}/blog"
    n = len(recs)
    sample_dates = [r["date"] for _, _, r in recs if r["date"]]
    span = f"{min(sample_dates)} to {max(sample_dates)}" if sample_dates else "dates unreadable"
    # --- inventory metric
    total12 = sum(by_month.values())
    last6 = list(by_month.items())[-6:]
    inv_text = (f"Blog inventory: {len(posts)} English post URLs; {total12} with a {('lastmod' if has_lastmod else 'publish date')} in the last 12 months "
                f"(last 6 months: {', '.join(f'{k} {v}' for k, v in last6)})")
    items.append({"type": "metric", "text": inv_text, "url": roots[0] if roots else blog_root,
                  "meta": {"metric": "posts_per_month", "by_month": by_month, "basis": basis, "label": "lastmod = updated or published" if has_lastmod else "publish date", "lastmod_bulk_stamp": str(stamp) if stamp else None,
                           "total_urls": len(posts), "urls_last_12m": total12, "listings_excluded": listings,
                           "non_english_excluded": skipped_locale, "distinct_lastmod_dates": distinct,
                           "sample_published_by_month": pub_by_month, "sample_span": span}})
    # --- post items
    for u, fu, r in recs:
        items.append({"type": "post", "text": tidy(f"{r['title']} | {r['cluster']} | {r['stage']}", 220), "quote": tidy(r["h1"] or r["title"], 160),
                      "url": fu, **({"date": r["date"].isoformat()} if r["date"] else {}),
                      "meta": {"author": r["author"], "author_note": r["author_note"], "words": r["words"], "h2": r["h2"], "h2_list": r["h2_list"],
                               "images": r["images"], "video": r["video"], "interactive": r["interactive"], "ctas": r["ctas"],
                               "product_links": r["product_links"], "schema": r["schema"], "faq": r["faq"], "tables": r["tables"],
                               "comparison_table": r["comparison_table"], "vs_title": r["vs_title"], "cluster": r["cluster"],
                               "stage": r["stage"], "ahrefs_traffic": r["ahrefs_traffic"],
                               "modified": r["modified"].isoformat() if r["modified"] else None}})
    if not recs:
        return write_source(domain, "blog", "partial", items, "; ".join(notes) + "; no post pages could be fetched")
    # --- aggregate metrics
    cl = Counter(r["cluster"] for _, _, r in recs)
    st = Counter(r["stage"] for _, _, r in recs)
    allrec = [v[1] for v in articles.values()] if not has_lastmod else []
    na = len(allrec)
    cl_all = Counter(r["cluster"] for r in allrec)
    st_all = Counter(r["stage"] for r in allrec)
    words_all = [r["words"] for r in allrec]
    words = [r["words"] for _, _, r in recs if r["words"]]
    med_words = int(statistics.median(words)) if words else 0
    med_h2 = statistics.median([r["h2"] for _, _, r in recs])
    n_video = sum(1 for _, _, r in recs if r["video"])
    n_inter = sum(1 for _, _, r in recs if r["interactive"])
    n_cta = sum(1 for _, _, r in recs if r["ctas_n"])
    n_plink = sum(1 for _, _, r in recs if r["product_links_n"])
    n_faq = sum(1 for _, _, r in recs if r["faq"])
    n_table = sum(1 for _, _, r in recs if r["tables"])
    cat_tot = Counter()
    for _, _, r in recs:
        for k in r["product_links"]:
            cat_tot[k] += 1
    cta_txt = Counter(c.lower() for _, _, r in recs for c in r["ctas"])
    schema_ct = Counter(t for _, _, r in recs for t in r["schema"])
    named = Counter(r["author"] for _, _, r in recs if r["author"])
    u0 = recs[0][1]
    items.append({"type": "metric", "text": f"Topic cluster mix over the {n} newest posts: " + ", ".join(f"{k} {v}" for k, v in cl.most_common()),
                  "url": u0, "meta": {"metric": "cluster_mix", "sample": n, "counts": dict(cl), "share_pct": {k: share(v, n) for k, v in cl.items()},
                                      "all_fetched": na, "counts_all_fetched": dict(cl_all),
                                      "share_pct_all_fetched": {k: share(v, na) for k, v in cl_all.items()}}})
    items.append({"type": "metric", "text": f"Funnel stage mix over the {n} newest posts: TOFU {st['TOFU']}, MOFU {st['MOFU']}, BOFU {st['BOFU']}",
                  "url": u0, "meta": {"metric": "stage_mix", "sample": n, "counts": {k: st.get(k, 0) for k in ("TOFU", "MOFU", "BOFU")},
                                      "share_pct": {k: share(st.get(k, 0), n) for k in ("TOFU", "MOFU", "BOFU")},
                                      "all_fetched": na, "counts_all_fetched": {k: st_all.get(k, 0) for k in ("TOFU", "MOFU", "BOFU")},
                                      "share_pct_all_fetched": {k: share(st_all.get(k, 0), na) for k in ("TOFU", "MOFU", "BOFU")}}})
    items.append({"type": "metric", "text": f"Median article length {med_words} words (median {med_h2:g} H2s) across {n} posts",
                  "url": u0, "meta": {"metric": "median_words", "median_words": med_words, "median_h2": med_h2, "min_words": min(words) if words else 0,
                                      "max_words": max(words) if words else 0, "sample": n,
                                      "median_words_all_fetched": int(statistics.median(words_all)) if words_all else None}})
    items.append({"type": "metric", "text": f"{share(n_video, n)}% of posts embed video ({n_video}/{n}); {share(n_inter, n)}% carry an interactive/AMP/other iframe embed ({n_inter}/{n})",
                  "url": u0, "meta": {"metric": "video_share", "with_video": n_video, "with_interactive": n_inter, "sample": n,
                                      "share_pct": share(n_video, n), "interactive_share_pct": share(n_inter, n),
                                      "avg_images": round(sum(r["images"] for _, _, r in recs) / n, 1)}})
    items.append({"type": "metric", "text": f"{share(n_cta, n)}% of posts have an in-article product CTA ({n_cta}/{n}); {share(n_plink, n)}% link to product pages ({n_plink}/{n}); "
                                            f"by type: " + (", ".join(f"{k} {v}" for k, v in cat_tot.most_common()) or "none"),
                  "url": u0, "meta": {"metric": "product_cta_share", "with_cta": n_cta, "with_product_link": n_plink, "sample": n,
                                      "cta_share_pct": share(n_cta, n), "product_link_share_pct": share(n_plink, n),
                                      "posts_by_link_type": dict(cat_tot), "top_cta_texts": dict(cta_txt.most_common(8)),
                                      "faq_share_pct": share(n_faq, n), "table_share_pct": share(n_table, n),
                                      "schema_counts": dict(schema_ct), "vs_in_title": sum(1 for _, _, r in recs if r["vs_title"]),
                                      "scope": "links and buttons inside the article body only; header, footer and mega-menu excluded"}})
    items.append({"type": "metric", "text": f"{len(named)} distinct named authors across {n} posts ({sum(named.values())} posts with a named byline, "
                                            f"{n - sum(named.values())} brand/team or none)" + (f"; the most frequent author wrote {named.most_common(1)[0][1]}" if named else ""),
                  "url": u0, "meta": {"metric": "authors", "distinct_named": len(named), "named_posts": sum(named.values()), "sample": n,
                                      "posts_per_author": sorted(named.values(), reverse=True)[:15]}})  # counts only, never names
    # --- traffic join
    blog_top = []
    for key, v in ahr.items():
        k, _ = blog_kind(v["url"])
        if k == "post":
            blog_top.append(v)
    blog_top.sort(key=lambda v: -v["traffic"])
    sample_keys = {norm_url(fu) for _, fu, _ in recs} | {norm_url(u) for u, _, _ in recs}
    total_top = sum(v["traffic"] for v in ahr.values())
    blog_tr = sum(v["traffic"] for v in blog_top)
    in_sample = [v for v in blog_top if norm_url(v["url"]) in sample_keys]
    if ahr:
        txt = (f"{len(blog_top)} blog URLs in the Ahrefs top {len(ahr)} pages, {blog_tr} of {total_top} estimated monthly visits "
               f"({share(blog_tr, total_top)}% of top-page traffic); {len(in_sample)} of the {n} newest posts are among them")
        if blog_top:
            txt += ": " + "; ".join(f"{urlparse(v['url']).path} {v['traffic']}" for v in blog_top[:5])
        items.append({"type": "metric", "text": tidy(txt, 700), "url": blog_top[0]["url"] if blog_top else u0,
                      "meta": {"metric": "top_blog_pages_by_traffic", "blog_pages": blog_top[:30], "blog_traffic": blog_tr, "top_pages_traffic": total_top,
                               "top_pages_count": len(ahr), "blog_share_pct": share(blog_tr, total_top), "newest_posts_in_top": len(in_sample),
                               "scope": "top pages as stored in ahrefs_organic.json (top 30 by organic traffic); not all blog traffic"}})
    notes.append("clusters by first-match keyword rules on title+slug, then H2s (comparison, case study, product update, holidays, AI, "
                 "engineering, measurement, templates, design, productivity, culture, how-to, marketing, else other); stage: BOFU = comparison/case study/pricing-demo-vs titles/brand-named tutorials, "
                 "TOFU = definitional/ideas/examples titles + holidays/other/templates, else MOFU (keyword heuristic, not human-labelled)")
    notes.append(f"basis for monthly counts: {basis}; sample = {n} newest posts ({span}); source of URLs: {source_desc}")
    if has_lastmod:
        notes.append("sample ordered by lastmod, so it can include older posts that were recently updated; see sample_published_by_month for true publish dates")
    if failed:
        notes.append(f"{len(failed)} sitemap files failed")
    if not named:
        notes.append("no named public bylines found")
    status = "ok" if n >= SAMPLE * 0.9 else "partial"
    return write_source(domain, "blog", status, items, tidy("; ".join(notes), 1800))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("domain")
    ap.add_argument("--alias", action="append", default=[])
    a = ap.parse_args()
    main(a.domain, a.alias)
