"""Run all script collectors for one domain (order matters: site before wayback/stack/github).

Usage: python run_collectors.py example.com --brand Example --category "form builder" [--alt "Old Name"] [--no-ai]
Agent collectors (ahrefs_*, earned, marketplaces, email_archive, corporate, ad_libraries) run from the skill.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

COL = Path(__file__).resolve().parent / "collectors"
PLAIN = ["site", "pricing", "wayback", "similarweb", "stack", "sitemap", "subdomains", "github", "social", "releases", "blog"]
BRANDED = ["hiring", "community", "news"] + (["linkedin"] if os.environ.get("OSINT_ENABLE_LINKEDIN") == "1" else [])  # LinkedIn: opt-in, see README


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("domain")
    ap.add_argument("--brand", required=True)
    ap.add_argument("--category", required=True)
    ap.add_argument("--alt", action="append", default=[])
    ap.add_argument("--no-ai", action="store_true", help="skip the paid LLM visibility collector")
    a = ap.parse_args()
    alts = [x for v in a.alt for x in ("--alt", v)]
    jobs = [[name, a.domain] for name in PLAIN] + [[name, a.domain, "--brand", a.brand, *alts] for name in BRANDED]
    if not a.no_ai:
        jobs.append(["ai_visibility", a.domain, "--brand", a.brand, "--category", a.category, *alts])
    failed = []
    for name, *args in jobs:
        r = subprocess.run([sys.executable, str(COL / f"{name}.py"), *args], cwd=COL)
        if r.returncode:
            failed.append(name)
    print("script collectors done" + (f"; FAILED: {failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
