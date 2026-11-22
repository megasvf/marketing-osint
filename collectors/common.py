"""Shared helpers for script collectors: fetch, page signal extraction, contract writer."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_LOCALE_FIXED = set()
_LOCALE_RX = re.compile(r"^/([a-z]{2}(?:-[a-z]{2})?)/", re.I)


def _geo_locale_redirected(req_url, final_url):
    """True when the site moved us into a non-English locale path we did not ask for (IP geo redirect)."""
    f, q = urlparse(final_url), urlparse(req_url)
    m = _LOCALE_RX.match(f.path)
    return bool(m and m.group(1).lower() not in ("en", "en-us", "en-gb") and not _LOCALE_RX.match(q.path))


def fetch(url, timeout=25):
    """Return (final_url, html) or (url, None) on failure.

    Geo guard: if the site redirects into a non-English locale (e.g. /ua/ from a Ukrainian IP), visit /en/ once
    per host so the site sets its locale cookie, then fetch the URL again.
    """
    try:
        r = SESSION.get(url, timeout=timeout, allow_redirects=True)
        host = urlparse(r.url).netloc
        if _geo_locale_redirected(url, r.url) and host not in _LOCALE_FIXED:
            _LOCALE_FIXED.add(host)
            SESSION.get(f"https://{host}/en/", timeout=timeout, allow_redirects=True)
            r = SESSION.get(url, timeout=timeout, allow_redirects=True)
        if r.status_code >= 400 or "html" not in r.headers.get("content-type", ""):
            return url, None
        if not r.encoding or r.encoding.lower() == "iso-8859-1":
            r.encoding = "utf-8"
        return r.url, r.text
    except requests.RequestException:
        return url, None


def clean(s, limit=None):
    s = re.sub(r"\s+", " ", s or "").strip()
    return s[:limit] if limit else s


def page_signals(html, base_url):
    """Extract the messaging layer of a page: title, meta, H1-H3, CTA labels, internal links."""
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript", "svg"]):
        t.decompose()

    def meta(name):
        tag = soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"property": name})
        return clean(tag.get("content")) if tag and tag.get("content") else ""

    heads = {h: [clean(x.get_text(" "), 160) for x in soup.find_all(h)] for h in ("h1", "h2", "h3")}
    ctas = []
    for a in soup.find_all(["a", "button"]):
        cls = " ".join(a.get("class", [])).lower()
        txt = clean(a.get_text(" "), 60)
        if txt and ("btn" in cls or "button" in cls or "cta" in cls or a.name == "button"):
            ctas.append(txt)
    links = []
    host = urlparse(base_url).netloc.replace("www.", "")
    for a in soup.find_all("a", href=True):
        u = urljoin(base_url, a["href"]).split("#")[0]
        if urlparse(u).netloc.replace("www.", "") == host:
            links.append((clean(a.get_text(" "), 60), u))
    body = clean(soup.get_text(" "))
    return {
        "title": clean(soup.title.get_text()) if soup.title else "",
        "description": meta("description") or meta("og:description"),
        "h1": [x for x in heads["h1"] if x],
        "h2": [x for x in heads["h2"] if x][:25],
        "h3": [x for x in heads["h3"] if x][:30],
        "ctas": list(dict.fromkeys(ctas))[:20],
        "links": links,
        "body_excerpt": body[:3000],
        "body_full": body,
    }


def write_source(domain, source, status, items, note=""):
    out = ROOT / "data" / domain / f"{source}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    bad = [i for i in items if not i.get("url")]
    if bad:
        raise ValueError(f"{source}: {len(bad)} items without url")
    payload = {"source": source, "domain": domain, "fetched_at": now_iso(),
               "status": status, "note": note, "items": items}
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[{status}] {source}: {len(items)} items -> {out}")
    return out
