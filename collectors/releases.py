"""Collector 14 - product release velocity: dated release-note / changelog entries (a momentum signal).

Sources, in order (all public, no keys):
  1. changelog page from data/<domain>/site.json (meta.kind == "changelog") and changelog-like links found on the
     home page and on docs / developers / help subdomains linked from it;
  2. direct probes (/changelog, /release-notes, /releases, /whats-new, /updates, /product-updates) on the domain
     and on docs / developers / changelog subdomains (accepted only when the page yields >= 2 dated entries);
  3. Beamer-hosted changelogs (changelog.<domain> style; JS-rendered, read through Beamer's public loadMoreNews);
  4. Zendesk help-center sections named "Product news and updates" / "Release notes" (public Help Center API);
  5. GitHub releases of the org in data/<domain>/github.json (unauthenticated REST, max 5 calls).

Entry extraction from HTML: <time datetime>, ISO dates, "Sep 11, 2025", "11 September 2025", "Oct 7 2026" next to a
heading. Pagination (Load More / next links, and per-product tabs) is followed until the oldest entry is
older than 18 months (MAX_PAGES 60 is only a safety net) per series; a 3-page cap is not enough for sites with 14 entries per
page that ship weekly, and the 90d-vs-prior-90d metric needs 180 days of history.

Output: one metric item (entries per month for 12 months, last 90d vs previous 90d, latest date, sources) plus one
"change" item per entry of the last 18 months (newest first, cap 120). Headline metrics use changelog + help-center
entries; GitHub releases are reported separately so a plugin release shown on both channels is not double counted.

Usage: python collectors/releases.py example.com
"""
import json
import re
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from urllib.parse import parse_qs, parse_qsl, urlencode, urljoin, urlparse, urlunparse, unquote

from bs4 import BeautifulSoup

from common import ROOT, SESSION, clean, fetch, write_source

MAX_PAGES = 60  # safety net only; pagination stops at entries older than 18 months
MAX_ITEMS = 120
MAX_CANDIDATES = 12
WINDOW_DAYS = 548  # ~18 months
TODAY = date.today()
CUTOFF = TODAY - timedelta(days=WINDOW_DAYS)

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
MON = r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?"
RX_ISO = re.compile(r"(?<!\d)(20\d\d)-(\d\d)-(\d\d)(?!\d)")
RX_MDY = re.compile(r"\b" + MON + r"\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d\d)\b", re.I)
RX_DMY = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+" + MON + r",?\s+(20\d\d)\b", re.I)
REL_RX = re.compile(r"changelog|release-?notes?|releases|what-?s-?new|whats-?new|product-?updates?|/updates?(?:/|$)", re.I)
REL_TEXT_RX = re.compile(r"change ?log|release notes?|what.?s new|product updates?|latest updates", re.I)
PROBES = ["/changelog", "/release-notes", "/releases", "/whats-new", "/updates", "/product-updates"]
SUBS = ["docs", "developers", "developer", "changelog", "updates", "help", "support", "whatsnew"]
ZD_SECTION_RX = re.compile(r"release|product (news|updates)|what.?s new|changelog|updates", re.I)
ZD_TITLE_RX = re.compile(r"release|update|new|now |introduc|launch|version|changelog|rename|rebrand", re.I)
NO_DASH = str.maketrans({"—": "-", "–": "-"})


def tidy(s, limit=200):
    return clean((s or "").translate(NO_DASH), limit)


# ---------------------------------------------------------------- dates

def first_date(text):
    """Earliest dated phrase in text -> (date, start, end) or None."""
    best = None
    for rx, kind in ((RX_ISO, "iso"), (RX_MDY, "mdy"), (RX_DMY, "dmy")):
        for m in rx.finditer(text or ""):
            try:
                if kind == "iso":
                    d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                elif kind == "mdy":
                    d = date(int(m.group(3)), MONTHS[m.group(1)[:3].lower()], int(m.group(2)))
                else:
                    d = date(int(m.group(3)), MONTHS[m.group(2)[:3].lower()], int(m.group(1)))
            except (ValueError, KeyError):
                continue
            if d > TODAY + timedelta(days=2):
                continue
            if best is None or m.start() < best[1]:
                best = (d, m.start(), m.end())
            break
    return best


def iso_attr(val):
    m = RX_ISO.search(val or "")
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


# ---------------------------------------------------------------- HTML entries

def heading_text(h):
    h = BeautifulSoup(str(h), "lxml")
    for t in h(["button", "svg", "script", "style"]):
        t.decompose()
    return clean(h.get_text(" "))


def parse_entries(html, page_url):
    """Dated entries (title, date, permalink) from a rendered changelog page."""
    soup = BeautifulSoup(html, "lxml")
    out = _parse_headings(soup, page_url, ["h2", "h3", "h4"])
    return out or _parse_headings(soup, page_url, ["h1"])


def _parse_headings(soup, page_url, tags):
    out, seen_nodes = [], set()
    for h in soup.find_all(tags):
        title = heading_text(h)
        if not (6 <= len(title) <= 300) or id(h) in seen_nodes:
            continue
        node, found, ok = h, None, False
        for _ in range(6):
            if node is None or node.name in ("body", "html", "[document]"):
                break
            if len(node.find_all(h.name)) > 1:
                break  # container spans several entries
            t = node.find("time", attrs={"datetime": True})
            d = iso_attr(t["datetime"]) if t else None
            if d:
                found, ok = (d, 0, 0), True
                break
            fd = first_date(node.get_text(" "))
            if fd:
                found, ok = fd, True
                break
            node = node.parent
        if not ok:
            continue
        d, s, e = found
        # a date written inside the heading itself is not part of the title
        hd = first_date(title)
        if hd:
            title = clean(title[:hd[1]] + " " + title[hd[2]:]).strip(" -:|")
        # permalink: share button > heading link > container id
        url = page_url
        share = node.find(attrs={"data-copy-url": True})
        a = h.find("a", href=True)
        if share:
            url = urljoin(page_url, share["data-copy-url"])
        elif a and not a["href"].startswith(("#", "javascript")):
            url = urljoin(page_url, a["href"])
        else:
            n, nid = node, None
            while n is not None and n.name not in ("body", "html", "[document]") and not nid:
                nid = n.get("id")
                n = n.parent
            nid = nid or h.get("id")
            if nid:
                url = page_url.split("#")[0] + "#" + nid
        if title and len(title) >= 6:
            out.append({"title": tidy(title), "date": d, "url": url})
    return out


def next_links(html, page_url):
    soup = BeautifulSoup(html, "lxml")
    cur = urlparse(page_url)
    res = []
    for a in soup.find_all("a", href=True):
        txt = clean(a.get_text(" ")).lower()
        rel = a.get("rel") or []
        if "next" in rel or re.search(r"load more|show more|older|next", txt):
            u = urljoin(page_url, a["href"]).replace("&amp;", "&")
            p = urlparse(u)
            if p.netloc == cur.netloc and u != page_url and "page=" in p.query:
                res.append(u)
    return res[:1]


def tab_variants(html, base_url):
    """per-product tabs: <button data-tab-link="plugin"> -> ?type=plugin."""
    soup = BeautifulSoup(html, "lxml")
    vals = [b["data-tab-link"] for b in soup.find_all(attrs={"data-tab-link": True})
            if "active" not in (b.get("class") or [])]
    out = []
    p = urlparse(base_url)
    for v in vals:
        q = dict(parse_qsl(p.query))
        if q.get("type") == v:
            continue
        q["type"] = v
        q.pop("page", None)
        out.append((v, urlunparse(p._replace(query=urlencode(q), fragment=""))))
    return out


def crawl_series(start_url, first_html=None, stream=None):
    """Follow Load More / next links; returns (entries, pages_fetched)."""
    entries, url, html, pages = [], start_url, first_html, 0
    while url and pages < MAX_PAGES:
        if html is None:
            url, html = fetch(url)
        if not html:
            break
        pages += 1
        es = parse_entries(html, url)
        for e in es:
            e["stream"] = stream
        entries += es
        if not es or min(e["date"] for e in es) < CUTOFF:
            break
        nxt = next_links(html, url)
        url, html = (nxt[0] if nxt else None), None
    return entries, pages


# ---------------------------------------------------------------- Beamer

def beamer_entries(html, page_url):
    m = re.search(r'_product_id\s*=\s*"([A-Za-z0-9]+)"', html or "")
    if not m or "getbeamer.com" not in html:
        return None, 0
    pid, host = m.group(1), urlparse(page_url)
    base = f"{host.scheme}://{host.netloc}"
    entries, pages = [], 0
    for pg in range(15):
        try:
            r = SESSION.get("https://app.getbeamer.com/loadMoreNews", timeout=25,
                            params={"app_id": pid, "language": "EN", "publicPage": "true", "page": pg,
                                    "basePath": "/en"})
        except Exception:
            break
        if r.status_code != 200 or not r.text.strip():
            break
        pages += 1
        soup = BeautifulSoup(r.text, "lxml")
        feats = soup.select("div.feature[data-post-title]")
        if not feats:
            break
        for f in feats:
            span = f.select_one(".featureDate span")
            fd = first_date(span.get_text(" ") if span else "")
            if not fd:
                continue
            link = None
            for a in f.select("a.shareLink[href]"):
                q = parse_qs(urlparse(a["href"].replace("&amp;", "&")).query)
                cand = (q.get("href") or q.get("url") or [None])[0]
                if cand and "getbeamer" not in cand and (cand.startswith(base) or "changelog" in cand):
                    link = unquote(cand)
                    break
            cat = clean(f.select_one(".featureDate .category").get_text(" ")) if f.select_one(".featureDate .category") else ""
            entries.append({"title": tidy(f.get("data-post-title")), "date": fd[0], "url": link or page_url,
                            "stream": cat or None})
        if min(e["date"] for e in entries) < CUTOFF:
            break
    return entries, pages


# ---------------------------------------------------------------- Zendesk

def zendesk_entries(host):
    """Product news / release sections of a Zendesk Help Center (public API)."""
    base = f"https://{host}/api/v2/help_center/en-us"
    try:
        r = SESSION.get(base + "/sections.json?per_page=100", timeout=25)
        if r.status_code != 200:
            return [], ("" if r.status_code in (403, 404) else f"{host}: help-center API HTTP {r.status_code}")
        secs = [s for s in r.json().get("sections", []) if ZD_SECTION_RX.search(s.get("name", ""))][:2]
    except Exception as e:
        return [], f"{host}: help-center API {type(e).__name__}"
    entries, skipped = [], 0
    for s in secs:
        try:
            r = SESSION.get(f"{base}/sections/{s['id']}/articles.json?per_page=100&sort_by=created_at&sort_order=desc",
                            timeout=25)
            arts = r.json().get("articles", []) if r.status_code == 200 else []
        except Exception:
            arts = []
        for a in arts:
            d = iso_attr(a.get("created_at"))
            if not d or d < CUTOFF:
                continue
            if not ZD_TITLE_RX.search(a.get("title", "")):
                skipped += 1  # FAQ-style article in a news section, not a release
                continue
            entries.append({"title": tidy(a["title"]), "date": d, "url": a["html_url"], "stream": s["name"]})
    return entries, (f"{host}: {skipped} non-release article(s) skipped" if skipped else "")


# ---------------------------------------------------------------- GitHub

def github_entries(domain):
    f = ROOT / "data" / domain / "github.json"
    if not f.exists():
        return [], "github.json missing"
    g = json.loads(f.read_text(encoding="utf-8"))
    org = None
    repos, tags_only = [], []
    for i in g.get("items", []):
        m = re.match(r"https://github\.com/([^/?#]+)", i.get("url", ""))
        if m and not org and i.get("text", "").startswith("GitHub org"):
            org = m.group(1)
        meta = i.get("meta") or {}
        if meta.get("repo") and meta.get("releases_12m"):
            repos.append(meta["repo"])
        elif meta.get("repo") and meta.get("git_tags"):
            tags_only.append(meta["repo"])
    if not org:
        return [], "no GitHub org in github.json"
    entries, calls, notes = [], 0, []
    for repo in repos[:5]:
        calls += 1
        try:
            r = SESSION.get(f"https://api.github.com/repos/{org}/{repo}/releases?per_page=100", timeout=25,
                            headers={"Accept": "application/vnd.github+json"})
        except Exception as e:
            notes.append(f"{repo}: {type(e).__name__}")
            continue
        if r.status_code != 200:
            notes.append(f"{repo}: HTTP {r.status_code}")
            continue
        for rel in r.json():
            d = iso_attr(rel.get("published_at") or rel.get("created_at"))
            if not d or d < CUTOFF or rel.get("draft"):
                continue
            entries.append({"title": tidy(f"{repo} {rel.get('name') or rel.get('tag_name')}"), "date": d,
                            "url": rel.get("html_url"), "stream": repo})
    if tags_only:
        notes.append(f"{', '.join(tags_only[:3])}: git tags only, no GitHub Releases (tag dates not fetched)")
    return entries, "; ".join(notes)


# ---------------------------------------------------------------- discovery

def clean_href(href):
    """Repair concatenated hrefs like 'https://x.comhttps://changelog.y.io/'."""
    parts = re.split(r"(?=https?://)", href)
    parts = [p for p in parts if p]
    return parts[-1] if parts else href


def collect_links(html, base):
    soup = BeautifulSoup(html or "", "lxml")
    out = []
    for a in soup.find_all("a", href=True):
        h = clean_href(a["href"])
        if h.startswith(("#", "mailto:", "javascript:", "tel:")):
            continue
        out.append((clean(a.get_text(" "), 80), urljoin(base, h).split("#")[0]))
    return out


def discover(domain):
    """Candidate changelog URLs, hosts of linked help centers, notes."""
    cands, notes, helps = [], [], set()
    reg = domain.replace("www.", "")

    def add(u, why):
        u = u.rstrip("/") if urlparse(u).path not in ("", "/") else u
        if u not in [c[0] for c in cands]:
            cands.append((u, why))

    f = ROOT / "data" / domain / "site.json"
    if f.exists():
        for i in json.loads(f.read_text(encoding="utf-8")).get("items", []):
            if (i.get("meta") or {}).get("kind") == "changelog":
                add(i["url"], "site.json")
    pages = [f"https://{domain}/"]
    seen_hosts = {domain}
    links = []
    home_url, home = fetch(pages[0])
    if home:
        links += collect_links(home, home_url)
    # subdomains linked from the home (docs / developers / help) plus default guesses
    sub_hosts = []
    for _, u in links:
        h = urlparse(u).netloc
        if h.endswith("." + reg) and h not in seen_hosts and h.split(".")[0] in SUBS:
            seen_hosts.add(h)
            sub_hosts.append(h)
        elif h and not h.endswith(reg) and re.match(r"(support|help)\.", h):
            helps.add(h)
    for s in SUBS[:5]:
        h = f"{s}.{reg}"
        if h not in seen_hosts:
            seen_hosts.add(h)
            sub_hosts.append(h)
    live_hosts = [domain]
    for h in sub_hosts[:8]:
        hu, html = fetch(f"https://{h}/")
        if html:
            live_hosts.append(urlparse(hu).netloc)
            links += collect_links(html, hu)
            if h.split(".")[0] == "changelog":
                add(hu, "subdomain")
    for text, u in links:
        p = urlparse(u)
        if "github.com" in p.netloc or "/search" in p.path:
            continue
        host_ok = p.netloc.endswith(reg) or p.netloc.endswith("getbeamer.com")
        if host_ok and (REL_RX.search(p.netloc + p.path) or REL_TEXT_RX.search(text)):
            add(u, f"linked ('{text[:30]}')")
        if re.match(r"(support|help)\.", p.netloc) or "/hc/" in p.path:
            helps.add(p.netloc)
    for h in dict.fromkeys(live_hosts):
        for p in PROBES:
            add(f"https://{h}{p}", "probe")
    return cands, sorted(helps), notes


def norm(u):
    p = urlparse(u)
    return (p.netloc.replace("www.", "") + p.path.rstrip("/")).lower()


# ---------------------------------------------------------------- main

def main(domain):
    notes, sources = [], {}  # sources: label -> {"url": ..., "entries": [...]}
    cands, helps, dnotes = discover(domain)
    notes += dnotes
    tried, fetched = set(), 0
    for u, why in cands:
        if fetched >= 30:
            break
        if norm(u) in tried:
            continue
        tried.add(norm(u))
        fu, html = fetch(u)
        fetched += 1
        if not html:
            continue
        p = urlparse(fu)
        if why == "probe":
            if "/search" in p.path or p.path in ("", "/") or not (REL_RX.search(p.path) or REL_RX.search(p.netloc)):
                continue  # soft redirect to home / search / blog
        if norm(fu) in tried and norm(fu) != norm(u):
            continue
        tried.add(norm(fu))
        entries, pages = [], 0
        bm, bpages = beamer_entries(html, fu)
        if bm is not None:
            entries, pages, kind = bm, bpages, "Beamer feed"
            if not entries and ".html" not in fu:
                entries, pages = [], bpages
        else:
            entries, pages = crawl_series(fu, html, None)
            kind = "html"
            for v, vu in tab_variants(html, fu):
                more, mp = crawl_series(vu, None, v)
                entries += more
                pages += mp
            # first series gets the active tab name if tabs exist
            if any(e["stream"] for e in entries):
                a = BeautifulSoup(html, "lxml").select_one(".active[data-tab-link]")
                for e in entries:
                    if e["stream"] is None and a:
                        e["stream"] = a.get("data-tab-link")
        sig = frozenset((e["date"], e["title"]) for e in entries)
        if len(sig) >= 2 and any(sig == frozenset((e["date"], e["title"]) for e in o["entries"])
                                 for o in sources.values()):
            continue  # alias of a feed already collected (e.g. /releases routed to the same changelog)
        if len(sig) >= 2:
            sources[fu] = {"entries": entries, "pages": pages, "kind": kind, "why": why}
        elif why != "probe":
            notes.append(f"{fu}: no dated entries parsed")
    # Zendesk help centers
    for h in helps[:5]:
        es, n = zendesk_entries(h)
        if n:
            notes.append(n)
        if es:
            sources[f"https://{h}/hc/en-us"] = {"entries": es, "pages": 1, "kind": "help center", "why": "linked"}
    # GitHub releases
    ges, gn = github_entries(domain)
    if gn:
        notes.append(gn)
    if ges:
        sources["https://github.com/releases"] = {"entries": ges, "pages": 0, "kind": "github", "why": "github.json"}

    if not sources:
        return write_source(domain, "releases", "unavailable", [],
                            "no release-note or changelog page with dated entries found; " + "; ".join(notes))

    # dedupe by (date, title) within each channel
    def channel(src):
        return "github" if src["kind"] == "github" else "primary"

    all_entries = []
    for url, src in sources.items():
        for e in src["entries"]:
            e["source"], e["channel"] = url, channel(src)
            all_entries.append(e)
    seen, entries = set(), []
    for e in sorted(all_entries, key=lambda x: (x["date"], x["title"]), reverse=True):
        k = (e["date"], e["title"].lower(), e["channel"])
        if k in seen:
            continue
        seen.add(k)
        entries.append(e)
    entries = [e for e in entries if e["date"] >= CUTOFF]
    prim = [e for e in entries if e["channel"] == "primary"]
    git = [e for e in entries if e["channel"] == "github"]
    head = prim or git
    d90, d180 = TODAY - timedelta(days=90), TODAY - timedelta(days=180)
    last = sum(1 for e in head if e["date"] > d90)
    prev = sum(1 for e in head if d180 < e["date"] <= d90)
    months = []
    y, m = TODAY.year, TODAY.month
    for _ in range(12):
        months.append(f"{y}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    months = months[::-1]
    by_month = {k: sum(1 for e in head if e["date"].strftime("%Y-%m") == k) for k in months}
    latest = max(e["date"] for e in head).isoformat()
    oldest = min(e["date"] for e in head).isoformat()
    cover_ok = min(e["date"] for e in head) <= d180
    by_source = {u: sum(1 for e in entries if e["source"] == u) for u in sources}
    trend = "n/a" if not prev else f"{(last - prev) / prev * 100:+.0f}%"
    # 90-day windows are the reliable signal; long totals can undercount when a site paginates partially
    summary = (f"Release velocity: {last} entries in the last 90 days vs {prev} in the previous 90 days ({trend}); "
               f"at least {len(head)} in 18 months (pagination may undercount); latest {latest}")
    main_url = next((u for u, s in sources.items() if channel(s) == "primary"), next(iter(sources)))
    items = [{"type": "metric", "text": summary, "url": main_url, "date": latest,
              "meta": {"by_month": by_month, "entries_90d": last, "entries_prev_90d": prev, "change_pct": trend,
                       "latest": latest, "oldest_collected": oldest, "history_covers_180d": cover_ok,
                       "entries_18m": len(head), "sources": by_source, "headline_channel": "changelog+help center"
                       if prim else "github",
                       "github_releases_18m": len(git),
                       "github_90d": sum(1 for e in git if e["date"] > d90),
                       "github_prev_90d": sum(1 for e in git if d180 < e["date"] <= d90)}}]
    # item cap: GitHub releases (a duplicate view of plugin notes on some sites) get at most 20 slots
    kept = sorted(prim[:MAX_ITEMS - min(len(git), 20)] + git[:20], key=lambda x: (x["date"], x["title"]), reverse=True) \
        if prim else entries[:MAX_ITEMS]
    for e in kept:
        items.append({"type": "change", "text": f"Release: {e['title']}", "quote": " ".join(e["title"].split()[:25]),
                      "url": e["url"], "date": e["date"].isoformat(),
                      "meta": {"stream": e.get("stream"), "channel": e["channel"], "source": e["source"]}})
    if len(entries) > len(kept):
        notes.append(f"{len(entries) - len(kept)} older entries beyond the {MAX_ITEMS}-item cap counted in metrics only")
    if not cover_ok:
        notes.append(f"history collected back to {oldest}, short of 180 days: 90d comparison understated")
    status = "ok" if prim and len(prim) >= 5 and cover_ok else "partial"
    if not prim:
        notes.append("only GitHub releases found; no changelog page")
    note = (f"{len(entries)} entries from {len(sources)} source(s): "
            + "; ".join(f"{u} [{s['kind']}, {s['pages']} page(s), {by_source[u]}]" for u, s in sources.items())
            + (". " + "; ".join(notes) if notes else ""))
    return write_source(domain, "releases", status, items, tidy(note, 1500))


if __name__ == "__main__":
    main(sys.argv[1])
