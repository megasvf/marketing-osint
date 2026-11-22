"""Collector 13 - subdomains from certificate transparency (crt.sh, Cert Spotter fallback): new hostnames hint at launches.

Names are deduped (wildcards stripped), first-seen = earliest certificate not_before per name.
CT shows only names that appear in public certificates; hosts behind a wildcard cert stay invisible.

Usage: python collectors/subdomains.py example.com
"""
import re
import sys
import time
from datetime import datetime, timedelta, timezone

from common import SESSION, write_source

HINTS = {"ai", "beta", "new", "app", "studio", "labs", "api", "sdk", "partners", "academy", "community", "events"}
RETRIES, TIMEOUT, MAX_CHANGES = 2, 60, 80
SPOTTER, SPOTTER_PAGES = "https://api.certspotter.com/v1/issuances", 5


def fetch_crt(domain):
    """Return (rows, error). 1 attempt + RETRIES retries."""
    url = f"https://crt.sh/?q=%25.{domain}&output=json"
    err = ""
    for attempt in range(RETRIES + 1):
        try:
            r = SESSION.get(url, timeout=TIMEOUT)
            if r.status_code == 200:
                return r.json(), ""
            err = f"HTTP {r.status_code}"
        except ValueError:
            err = "response was not JSON"
        except Exception as e:
            err = type(e).__name__
        if attempt < RETRIES:
            time.sleep(4 * (attempt + 1))
    return None, f"crt.sh failed after {RETRIES + 1} attempts ({err})"


def fetch_spotter(domain):
    """Cert Spotter fallback: rows shaped like crt.sh rows plus _url (API page). Returns (rows, error)."""
    rows, after, err = [], "", ""
    for _ in range(SPOTTER_PAGES):
        url = f"{SPOTTER}?domain={domain}&include_subdomains=true&expand=dns_names" + (f"&after={after}" if after else "")
        try:
            r = SESSION.get(url, timeout=TIMEOUT)
            if r.status_code != 200:
                err = f"HTTP {r.status_code}"
                break
            page = r.json()
        except ValueError:
            err = "response was not JSON"
            break
        except Exception as e:
            err = type(e).__name__
            break
        if not page:
            break
        rows += [{"name_value": "\n".join(x.get("dns_names") or []), "not_before": x.get("not_before"), "_url": url}
                 for x in page]
        after = page[-1]["id"]
    return (rows or None), err


def hints_for(name, domain):
    label = name[: -len(domain)].rstrip(".")
    toks = set(re.split(r"[.\-_\d]+", label))
    return sorted(toks & HINTS)


def main(domain):
    rows, err = fetch_crt(domain)
    src = "crt.sh"
    if rows is None:
        rows, err2 = fetch_spotter(domain)
        if rows is None:
            return write_source(domain, "subdomains", "unavailable", [], f"{err}; Cert Spotter also failed ({err2 or 'no issuances'})")
        src = f"Cert Spotter ({err})"
        if err2:
            src += f"; paging stopped early ({err2})"
    first, page_url = {}, {}
    for row in rows:
        nb = (row.get("not_before") or "")[:10]
        if not nb:
            continue
        for raw in (row.get("name_value") or "").splitlines():
            name = raw.strip().lower().lstrip("*.").strip(".")
            if not name or "@" in name or not (name == domain or name.endswith("." + domain)):
                continue
            if name not in first or nb < first[name]:
                first[name] = nb
                page_url[name] = row.get("_url")
    if not first:
        return write_source(domain, "subdomains", "unavailable", [], f"{src} returned no certificate names for this domain")
    cutoff = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%d")
    new = sorted(((d, n) for n, d in first.items() if d >= cutoff and n != domain), reverse=True)
    hinted_all = {n: hints_for(n, domain) for n in first if n != domain}
    hinted_all = {n: h for n, h in hinted_all.items() if h}
    items = []
    for d, n in new[:MAX_CHANGES]:
        h = hints_for(n, domain)
        items.append({"type": "change", "text": f"New subdomain {n} first seen {d}"
                                               + (f" (launch hint: {', '.join(h)})" if h else ""),
                      "url": page_url.get(n) or f"https://crt.sh/?q={n}", "date": d, "meta": {"name": n, "hints": h}})
    ex = sorted(hinted_all.items(), key=lambda kv: first[kv[0]], reverse=True)[:12]
    items.append({"type": "metric",
                  "text": f"{len(first)} distinct names in certificate transparency, {len(new)} first seen in the last 365 days, "
                          f"{len(hinted_all)} with launch-hinting words",
                  "url": rows[0].get("_url") or f"https://crt.sh/?q=%25.{domain}",
                  "meta": {"total_names": len(first), "new_365d": len(new), "cutoff": cutoff,
                           "hinting": {n: {"first_seen": first[n], "hints": h} for n, h in ex}}})
    note = (f"{src}, {len(rows)} certificate rows; first-seen = earliest cert date, not host creation; "
            f"wildcard-covered hosts are invisible")
    if len(new) > MAX_CHANGES:
        note += f"; {len(new) - MAX_CHANGES} older new names omitted from change items (count in the summary metric)"
    if src != "crt.sh" and len(rows) >= SPOTTER_PAGES * 100:
        note += f"; capped at {SPOTTER_PAGES} Cert Spotter pages, older certificates not read"
    return write_source(domain, "subdomains", "ok" if src == "crt.sh" else "partial", items, note)


if __name__ == "__main__":
    main(sys.argv[1])
