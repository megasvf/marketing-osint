"""Collector - pricing page in both billing modes (monthly and yearly), via Playwright (pricing_capture.js).

The site collector sees only the billing mode the page loads with (often yearly). This one clicks the
Monthly / Yearly toggle and keeps the price lines of each mode, so reports never show a yearly price as monthly.

Usage: python collectors/pricing.py example.com
"""
import json
import re
import subprocess
import sys
from pathlib import Path

from common import ROOT, write_source

SCRIPT = Path(__file__).resolve().parent / "pricing_capture.js"
PRICE = re.compile(r"(?:[$€£¥₴]\s?\d|\d\s?(?:[$€£¥₴]|USD|EUR|GBP)\b)")
MAX_PER_MODE = 40


def pricing_url(domain):
    site = ROOT / "data" / domain / "site.json"
    if site.exists():
        try:
            for it in json.loads(site.read_text(encoding="utf-8")).get("items", []):
                u = it.get("url", "")
                if "pricing" in u.lower() and u.startswith("http"):
                    return u.split("#")[0]
        except ValueError:
            pass
    return f"https://{domain}/pricing"


def price_lines(text):
    """[(plan_hint, price_line)] - lines with a currency sign and a number, plus the nearest short heading above."""
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    out, seen = [], set()
    for i, line in enumerate(lines):
        if not PRICE.search(line) or len(line) > 200 or line in seen:
            continue
        seen.add(line)
        hint = ""
        for prev in reversed(lines[max(0, i - 6):i]):
            if len(prev) <= 30 and prev.lower() not in ("recommended", "most popular", "popular", "new") and not re.search(r"\d", prev) and not PRICE.search(prev):
                hint = prev
                break
        out.append((hint, line))
    return out[:MAX_PER_MODE]


def run_capture(url):
    try:
        p = subprocess.run(["node", str(SCRIPT), url], capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        return None, "node capture timed out after 90 s"
    except OSError as e:
        return None, f"node not runnable ({type(e).__name__})"
    try:
        return json.loads(p.stdout.strip().splitlines()[-1]), ""
    except (ValueError, IndexError):
        return None, f"capture gave no JSON: {(p.stderr or p.stdout)[-200:].strip()}"


def main(domain):
    url = pricing_url(domain)
    res, err = run_capture(url)
    if res is None or res.get("error") or not (res.get("modes") or {}).get("default"):
        why = err or (res or {}).get("error") or "empty page text"
        return write_source(domain, "pricing", "unavailable", [], f"{url}: {why}")
    modes, default = res["modes"], res.get("default_mode", "unknown")
    lines = {m: price_lines(modes.get(m)) for m in ("default", "monthly", "yearly")}
    if not any(lines.values()):
        return write_source(domain, "pricing", "unavailable", [], f"{url}: page text has no price lines (modes tried: default)")
    got = [m for m in ("monthly", "yearly") if modes.get(m)]
    same = len(got) == 2 and lines["monthly"] == lines["yearly"]
    # Default text duplicates a named mode when the default mode is known and captured.
    show = [] if same else got[:]
    if default not in show or default == "unknown":
        show.insert(0, "default")
    items = []
    # A price that reads the same in both modes is not switched by the toggle (e.g. annual-only plans):
    # label it so a monthly-mode capture is never read as "billed monthly".
    both = set(lines.get("monthly") or []) & set(lines.get("yearly") or []) if "monthly" in got and "yearly" in got else set()
    for hint, line in sorted(both, key=lambda hl: (lines["yearly"].index(hl) if hl in lines["yearly"] else 0)):
        items.append({"type": "claim", "text": f"same in both modes: {line}", "quote": " ".join(line.split()[:25]), "url": url,
                      "meta": {"billing_mode": "unchanged_by_toggle", "default_mode": default, "plan_hint": hint,
                               "basis": "price did not change when the billing toggle was switched; read the plan's own wording for its billing period"}})
    for m in show:
        for hint, line in lines[m]:
            if (hint, line) in both:
                continue
            items.append({"type": "claim", "text": f"{m}: {line}", "quote": " ".join(line.split()[:25]),
                          "url": res.get("final_url") or url,
                          "meta": {"billing_mode": m, "default_mode": default, "plan_hint": hint}})
    ok = len(got) == 2 and not same
    note = (f"Playwright capture of {url}; default toggle: {default}; modes captured: default"
            + "".join(f", {m}" for m in got) + "; toggles found: "
            + (", ".join(dict.fromkeys(t["text"] for t in res.get("toggles_found", []))) or "none"))
    if same:
        note += "; monthly and yearly price lines are identical, so the toggle click changed nothing"
    elif not ok:
        note += "; missing: " + ", ".join(m for m in ("monthly", "yearly") if m not in got) + " (not captured, none invented)"
    if default == "unknown":
        note += "; default billing mode could not be detected, 'default' prices have unknown billing mode"
    return write_source(domain, "pricing", "ok" if ok else "partial", items, note)


if __name__ == "__main__":
    main(sys.argv[1])
