"""Run-cost ledger: paid APIs / tools used per company run, shown in the report footer.

  python costs.py <domain> <tool> <amount> <unit> "<note>"     # append one entry (agents call this)
  python costs.py <domain> --show

Entries live in data/<domain>/_run_cost.json (underscore = not a collector file):
  {"date": "YYYY-MM-DD", "tool": "Ahrefs API", "amount": 6570, "unit": "units", "billing": "plan quota", "note": "..."}
`billing`: "pay per use" (API keys billed per call/token), "plan quota" (subscription units), "subscription" (flat), "cache" (no new spend).
"""
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BILLING = {"Ahrefs API": "plan quota", "SimilarWeb (RapidAPI)": "pay per use", "OpenAI API": "pay per use",
           "Gemini API": "pay per use", "xAI API": "pay per use"}


def path(domain):
    return ROOT / "data" / domain / "_run_cost.json"


def load(domain):
    f = path(domain)
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []


def record(domain, tool, amount, unit, note="", billing=None, day=None):
    rows = load(domain)
    rows.append({"date": day or date.today().isoformat(), "tool": tool, "amount": amount, "unit": unit,
                 "billing": billing or BILLING.get(tool, "pay per use"), "note": note})
    path(domain).parent.mkdir(parents=True, exist_ok=True)
    path(domain).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


def summary(domain):
    """[(tool, billing, total amount, unit, notes)] aggregated per tool+unit."""
    agg = {}
    for r in load(domain):
        k = (r["tool"], r["unit"])
        a = agg.setdefault(k, {"billing": r.get("billing", ""), "amount": 0, "notes": []})
        a["amount"] += r.get("amount") or 0
        if r.get("note"):
            a["notes"].append(r["note"])
    return [(t, v["billing"], v["amount"], u, v["notes"]) for (t, u), v in agg.items()]


if __name__ == "__main__":
    d = sys.argv[1]
    if "--show" in sys.argv:
        for row in summary(d):
            print(row)
    else:
        tool, amount, unit = sys.argv[2], float(sys.argv[3]), sys.argv[4]
        record(d, tool, int(amount) if amount.is_integer() else amount, unit, sys.argv[5] if len(sys.argv) > 5 else "")
        print("recorded")
