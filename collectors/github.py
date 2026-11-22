"""Collector 13 — developer-marketing footprint: GitHub org repos, stars, release cadence.

Handles come from github.com links on the company site (data/<domain>/site.json plus a fresh fetch of the home,
docs and developer pages), then name guesses. A handle is accepted only when its name or website matches the brand
or domain. Uses `gh api` when the CLI is logged in (no rate limit trouble), otherwise unauthenticated REST.

Usage: python collectors/github.py example.com [--brand "Example"] [--alt "Old Name"]
"""
import argparse
import json
import re
import subprocess
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from common import ROOT, SESSION, fetch, write_source

API = "https://api.github.com"
SKIP = {"features", "sponsors", "about", "pricing", "login", "join", "topics", "marketplace", "enterprise",
        "orgs", "apps", "settings", "customer-stories", "readme", "collections", "trending"}


def args_brand():
    ap = argparse.ArgumentParser()
    ap.add_argument("domain")
    ap.add_argument("--brand")
    ap.add_argument("--alt", action="append", default=[])
    a = ap.parse_args()
    brand = a.brand or a.domain.split(".")[0].capitalize()
    return a.domain, brand, a.alt


def gh(path):
    """GET a GitHub REST path. Returns (json, via) or (None, error text)."""
    try:
        p = subprocess.run(["gh", "api", path], capture_output=True, text=True, encoding="utf-8", timeout=60)
        if p.returncode == 0:
            return json.loads(p.stdout), "gh"
        err = (p.stderr or p.stdout)[:80]
    except Exception as e:
        err = type(e).__name__
    try:
        r = SESSION.get(API + path, timeout=25, headers={"Accept": "application/vnd.github+json"})
        if r.status_code == 200:
            return r.json(), "rest"
        return None, f"{path}: HTTP {r.status_code} (gh: {err})"
    except Exception as e:
        return None, f"{path}: {type(e).__name__}"


def handles_from_site(domain):
    found = Counter()
    f = ROOT / "data" / domain / "site.json"
    if f.exists():
        for m in re.finditer(r"github\.com/([A-Za-z0-9_.-]+)", f.read_text(encoding="utf-8")):
            found[m.group(1)] += 1
    pages = [f"https://{domain}/"] + [f"https://{p}.{domain}/" for p in ("docs", "developers", "developer", "dev", "api")] + \
            [f"https://{domain}/{p}" for p in ("developers", "docs", "developer", "api")]
    fetched = []
    for u in pages:
        fu, h = fetch(u)
        if h:
            fetched.append(fu)
            for m in re.finditer(r"github\.com/([A-Za-z0-9_.-]+)", h):
                found[m.group(1)] += 1
    return [h for h, _ in found.most_common() if h.lower() not in SKIP], fetched


def matches(info, domain, terms):
    label = domain.split(".")[0].lower()
    hay = " ".join(str(info.get(k) or "") for k in ("login", "name", "blog")).lower()
    return label in hay or domain.lower() in hay or any(t.lower().replace(" ", "") in hay.replace(" ", "") for t in terms)


def find_owner(domain, terms):
    linked, fetched = handles_from_site(domain)
    label = domain.split(".")[0].lower()
    guesses = [label, f"{label}inc", f"{label}-inc", f"{label}sdk", f"{label}-io", f"{label}hq", f"{label}app",
               f"{label}-email", f"get{label}"] + [t.lower().replace(" ", "") for t in terms]
    tried, errs, weak = [], [], None
    for h in list(dict.fromkeys(linked + guesses)):
        info, via = gh(f"/users/{h}")  # /users also answers for organizations and needs no extra token scope
        if info and matches(info, domain, terms):
            kind = "orgs" if info.get("type") == "Organization" else "users"
            # strong = linked from the site, or its website field points at the domain; else keep looking
            if h in linked or label in str(info.get("blog") or "").lower():
                return info, kind, via, linked, fetched, errs
            weak = weak or (info, kind, via)
        if not info:
            errs.append(via)
        tried.append(h)
    if weak:  # name-only match: accepted but flagged in the note by the caller
        return (*weak, linked, fetched, errs)
    return None, None, None, linked, fetched, errs


def main(domain, brand, alts):
    terms = [brand] + alts
    info, kind, via, linked, fetched, errs = find_owner(domain, terms)
    if not info:
        return write_source(domain, "github", "unavailable", [],
                            f"no verified GitHub org/user; handles linked from site {linked[:5]}; fetched {len(fetched)} pages; "
                            f"API errors {sorted(set(errs))[:3]}")
    login = info["login"]
    repos, _ = gh(f"/{kind}/{login}/repos?per_page=100&sort=pushed&type=public")
    repos = [r for r in (repos or []) if not r.get("fork")]
    top = sorted(repos, key=lambda r: r["stargazers_count"], reverse=True)[:15]
    today = datetime.now(timezone.utc)
    d90, d365 = (today - timedelta(days=90)).isoformat(), (today - timedelta(days=365)).isoformat()
    total_stars = sum(r["stargazers_count"] for r in repos)
    active90 = [r for r in repos if (r.get("pushed_at") or "") >= d90]
    items = [{"type": "page", "text": f"GitHub {kind[:-1]} {login}: {info.get('public_repos')} public repos, {total_stars} stars across own non-fork repos",
              "quote": info.get("description") or info.get("bio") or "", "url": f"https://github.com/{login}",
              "meta": {"login": login, "public_repos": info.get("public_repos"), "followers": info.get("followers"),
                       "blog": info.get("blog"), "created_at": (info.get("created_at") or "")[:10]}}]
    for r in top:
        items.append({"type": "page",
                      "text": f"{r['name']}: {r['stargazers_count']} stars, {r['forks_count']} forks, last push {(r.get('pushed_at') or '')[:10]}",
                      "quote": r.get("description") or "", "url": r["html_url"], "date": (r.get("pushed_at") or "")[:10],
                      "meta": {"repo": r["name"], "stars": r["stargazers_count"], "forks": r["forks_count"],
                               "language": r.get("language"), "archived": r.get("archived"),
                               "open_issues": r.get("open_issues_count")}})
    cadence = []
    for r in top[:3]:
        rel, _ = gh(f"/repos/{login}/{r['name']}/releases?per_page=100")
        rel = [x for x in (rel or []) if not x.get("draft")]
        recent = [x for x in rel if (x.get("published_at") or "") >= d365]
        latest = rel[0] if rel else None
        tags = None
        if not rel:
            t, _ = gh(f"/repos/{login}/{r['name']}/tags?per_page=100")
            tags = len(t) if t is not None else None
        cadence.append((r["name"], len(recent), latest["tag_name"] if latest else None,
                        (latest.get("published_at") or "")[:10] if latest else None))
        items.append({"type": "metric",
                      "text": f"{r['name']}: {len(recent)} releases in the last 12 months; latest {latest['tag_name'] if latest else 'none'}"
                              + (f" on {(latest.get('published_at') or '')[:10]}" if latest else "")
                              + (f" ({tags}{"+" if tags >= 100 else ""} git tags, GitHub Releases not used)" if tags else ""),
                      "url": f"{r['html_url']}/releases", "date": (latest.get("published_at") or "")[:10] if latest else None,
                      "meta": {"repo": r["name"], "releases_12m": len(recent), "latest_tag": latest["tag_name"] if latest else None, "git_tags": tags}})
    langs = Counter(r["language"] for r in repos if r.get("language")).most_common(4)
    items.append({"type": "metric",
                  "text": f"Developer-marketing signal: {len(active90)} of {len(repos)} own repos pushed in the last 90 days; "
                          f"{sum(c[1] for c in cadence)} releases in 12 months across the top 3 repos by stars; main languages "
                          + ", ".join(f"{l} ({n})" for l, n in langs),
                  "url": f"https://github.com/{login}?tab=repositories&sort=stargazers",
                  "meta": {"repos_pushed_90d": len(active90), "own_repos": len(repos), "total_stars": total_stars,
                           "releases_top3": cadence, "date_checked": date.today().isoformat()}})
    note = (f"{kind[:-1]} {login} verified by name/website match; found via {'site links' if login in linked else 'name guess'}; "
            f"API via {via}; forks excluded; listing capped at 100 repos; releases counted for top 3 repos by stars; "
            f"only public data, stars are a popularity proxy")
    return write_source(domain, "github", "ok", items, note)


if __name__ == "__main__":
    main(*args_brand())
