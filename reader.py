"""Optional reader profile: the company a report is written for.

With a profile, the reports add "What it means for <reader>": a battlecard with a price check (competitor),
a borrow list (benchmark), an ideal-customer fit table (prospect), shared audience and joint ideas (partner).
Without one, the report stays neutral and those blocks speak to "you".

Where the profile comes from, first hit wins:
  1. env OSINT_READER = path to a JSON file
  2. reader.json in the repo root (git-ignored: it is yours)
Shape: see reader.example.json. Every field is optional except "name".
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def path():
    p = os.environ.get("OSINT_READER")
    return Path(p) if p else ROOT / "reader.json"


def load():
    """The reader profile as a dict, or {} when there is none."""
    f = path()
    if not f.exists():
        return {}
    d = json.loads(f.read_text(encoding="utf-8"))
    return d if d.get("name") else {}


def name(analysis=None):
    """Reader name for headings: the one stored in the analysis, else the profile, else 'you'."""
    n = (analysis or {}).get("reader") or load().get("name")
    return n if n and n != "none" else ""


def text():
    """The whole profile as one string (factcheck accepts reader numbers that appear here)."""
    d = load()
    return json.dumps(d, ensure_ascii=False) if d else ""
