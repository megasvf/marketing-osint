"""Deterministic fact-check gate for analysis.json / compare_analysis.json (runs before the LLM fact-check).

Catches the error classes found by manual fact-checks on 2026-10-08:
  Q  quote not verbatim in the cited collector item (paraphrase shown as a quote)
  N  a number in a claim that appears nowhere in the cited items (wrong or stale figure)
  W  window/basis traps: Ahrefs current partial month used, "rank" for AI mention order, "stopped" without a date,
     LinkedIn all-time vs 30-day counts mixed without a window word
  T  tone: words that imply intent about a company ("misleading", "deceptive", "inconsistent", "lies", "fake")
  D  em/en dashes, hype words
Not blocking, printed for the LLM fact-check (and written by --targets):
  F  freshness: deal, funding and leadership claims; the LLM fact-check must open the newest primary source

Usage: python factcheck.py example.com [--fix-quotes]   (single report; --fix-quotes blanks non-verbatim quotes; --add-evidence attaches items that carry flagged numbers)
       python factcheck.py --compare a.com b.com
       python factcheck.py example.com --targets   (writes data/<domain>/_factcheck_targets.json: the claims the LLM fact-check must open)
Exit 1 when any Q/N/W/T/D issue is found; the report lists JSON path, code and detail.
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

import reader as RD

ROOT = Path(__file__).resolve().parent
HYPE = r"\b(revolutionary|seamless(ly)?|unlock|leverage|game[- ]changer|cutting[- ]edge|world[- ]class|supercharge)\b"
TONE = r"\b(misleading|deceptive|dishonest|lies|lying|fake|internally inconsistent|inflated claims?)\b"


def collector_index(domains):
    """url -> list of item texts (text + quote + meta dump) across the domains' collector files."""
    idx = {}
    for d in domains:
        for f in (ROOT / "data" / d).glob("*.json"):
            if f.name.startswith("_") or f.name in ("analysis.json", "changes.json"):
                continue
            for i in json.loads(f.read_text(encoding="utf-8")).get("items", []):
                blob = " ".join([i.get("text") or "", i.get("quote") or "", json.dumps(i.get("meta", {}), ensure_ascii=False)])
                idx.setdefault(i.get("url"), []).append(blob)
    return idx


def norm(s):
    return re.sub(r"\s+", " ", (s or "").replace("’", "'").replace("“", '"').replace("”", '"')).strip().lower()


COUNT_NOUN = re.compile(r"\s+(?:of\s+(?:the\s+)?\d|open\b|roles?\b|jobs?\b|listings?\b|ads?\b|creatives?\b|reviews?\b|keywords?\b|"
                        r"prompts?\b|answers?\b|posts?\b|videos?\b|pages?\b|customers?\b|employees?\b|people\b|staff\b|"
                        r"sources?\b|citations?\b|domains?\b|links?\b|releases?\b|mentions?\b|members?\b|countries\b|cities\b|"
                        r"offices?\b|locales?\b|languages?\b|plans?\b|integrations?\b|apps?\b|sessions?\b|webinars?\b|episodes?\b)", re.I)
FRESH = re.compile(r"\b(acquir\w*|acquisition|merger|merged|funding|raised|valuation|tender|ipo|went public|"
                   r"appointed|resigned|stepped down|new ceo|chief executive|layoffs?|rebrand\w*|renamed)\b", re.I)


def numbers(s):
    """Significant numbers in a string: 3+ digit figures, decimals, percents, and 10-99 when they count something
    ("73 open roles", "21 of 170"), normalised, commas dropped."""
    out = set()
    s = re.sub(r"\b\d{4}-\d{2}(?:-\d{2})?\b", " ", s or "")  # ISO dates are dates, not counts
    s = re.sub(r"\b(Fortune|Forrester Wave|Top|Inc\.?|ISO|SOC|WCAG|CVE-\d+-?)\s*\d+(\.\d+)?\b", " ", s or "", flags=re.I)  # names, not figures
    for m in re.finditer(r"(?<![\w.])\$?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(k|m|%)?", s, re.I):
        raw, suf = m.group(1).replace(",", ""), (m.group(2) or "").lower()
        try:
            v = float(raw)
        except ValueError:
            continue
        if suf == "%" or "." in raw or v >= 100 or (10 <= v < 100 and not suf and COUNT_NOUN.match(s, m.end())):
            out.add((v, suf))
    return out


def blob_numbers(blob):
    vals = []
    for m in re.finditer(r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)", blob):
        try:
            vals.append(float(m.group(1).replace(",", "")))
        except ValueError:
            pass
    return vals


def num_in(v, suf, blob):
    if suf == "%" and any(abs(x - v) <= 0.6 or (x < 1 and abs(x * 100 - v) <= 0.6) for x in blob_numbers(blob)):
        return True  # rounded percent (77% vs 76.9%)
    target = v * (1000 if suf == "k" else 1e6 if suf == "m" else 1)
    if suf != "%" and target >= 1000 and any(abs(x - target) / target <= 0.015 for x in blob_numbers(blob)):
        return True  # rounded figure (about 431k vs 430,571)
    pats = {f"{v:g}", f"{v:,.0f}" if v >= 1000 else f"{v:g}"}
    if suf == "k":
        pats |= {f"{v * 1000:,.0f}", f"{v * 1000:.0f}"}
    if suf == "m":
        pats |= {f"{v * 1e6:,.0f}"}
    return any(p.lower() in blob for p in pats)


def own_strings(node):
    """All strings of a claim node (nested dicts/lists included) except its evidence and link fields."""
    out = []
    for k, v in node.items():
        if k in ("evidence", "url", "source", "domain"):
            continue
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict):
            out += own_strings(v)
        elif isinstance(v, list):
            out += [x for x in v if isinstance(x, str)]
    return out


def walk(o, path=""):
    if isinstance(o, dict):
        yield path, o
        for k, v in o.items():
            yield from walk(v, f"{path}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from walk(v, f"{path}[{i}]")


READER_IDX = {}


def check(doc, domains):
    idx = collector_index(domains)
    READER_IDX.clear()
    rd = RD.load().get("domain")
    if rd and (ROOT / "data" / rd).exists() and rd not in domains:
        READER_IDX.update(collector_index([rd]))
    issues = []
    cur_month = date.today().strftime("%Y-%m")
    for path, node in walk(doc):
        evs = node.get("evidence") if isinstance(node, dict) else None
        if evs:
            blobs = [norm(b) for e in evs for b in idx.get(e.get("url"), [])]
            if path.startswith((".battlecard", ".lens_block")):
                # reader material may cite the reader profile (its own prices) and the reader's outside-in data
                blobs += [norm(RD.text())]
                blobs += [norm(b) for bl in READER_IDX.values() for b in bl]
            for k, e in enumerate(evs):
                q = norm(e.get("quote"))
                if q and not any(q.rstrip(".") in b for b in (norm(x) for x in idx.get(e.get("url"), []))):
                    issues.append((f"{path}.evidence[{k}]", "Q", f"quote not verbatim in cited item: {e.get('quote')[:90]}"))
            # numbers in this node's own text fields must appear in the cited items
            own = " ".join(own_strings(node))
            joined = " ".join(blobs)
            for v, suf in numbers(own):
                if not num_in(v, suf, joined) and not (2000 <= v <= 2100 and not suf):
                    issues.append((path, "N", f"number {v:g}{suf} not found in the cited items"))
        if isinstance(node, dict):
            mirrored = ".evidence[" in path or path.startswith(".sources") or path.startswith(".gaps")
            for kk, v in node.items():
                if not isinstance(v, str) or kk in ("url",):
                    continue
                p = f"{path}.{kk}"
                if mirrored and kk in ("text", "note", "reason"):
                    if "\u2014" in v or "\u2013" in v:
                        issues.append((p, "D", "em/en dash"))
                    continue
                if "—" in v or "–" in v:
                    issues.append((p, "D", "em/en dash"))
                if "�" in v:
                    issues.append((p, "D", "replacement character (broken encoding) in text"))
                if re.search(HYPE, v, re.I):
                    issues.append((p, "D", f"hype word: {re.search(HYPE, v, re.I).group(0)}"))
                if re.search(TONE, v, re.I) and kk != "quote":
                    issues.append((p, "T", f"intent-implying word: {re.search(TONE, v, re.I).group(0)}"))
                if re.search(r"\b(average |avg )?rank(ed)?\b", v, re.I) and re.search(r"\b(AI|gpt|gemini|grok|answer)", v, re.I) \
                        and not re.search(r"mention order|not a rank|own (ranked )?list|answer'?s own|own ranking", v, re.I):
                    issues.append((p, "W", "AI result described as 'rank': say 'in the answer's own ranked list' (ai_visibility rank) or 'mention order'"))
                if kk != "quote" and re.search(r"\bstopped\b|\bswitched off\b|\bturned off\b", v, re.I):  # verbatim quotes exempt
                    issues.append((p, "W", "'stopped' needs a dated source; prefer 'not observed since <date>'"))
                if re.search(cur_month + r"(?!-\d)", v) and re.search(r"organic traffic|visits|traffic", v, re.I):
                    issues.append((p, "W", f"uses the current partial month {cur_month} for Ahrefs traffic"))
                if re.search(r"linkedin", v, re.I) and re.search(r"\b\d{2,4}\b ads?", v) and not re.search(r"all[- ]time|library|in \d+ days|sample", v, re.I):
                    issues.append((p, "W", "ad count without a window (all-time / last 30 days / sample)"))
    return issues


def targets(doc):
    """Claims the LLM fact-check must open, in priority order: headline numbers, money, passport, then fresh-news claims."""
    out, seen = [], set()

    def add(path, node, why):
        if path in seen or not isinstance(node, dict):
            return
        seen.add(path)
        text = " | ".join(x for x in own_strings(node) if x)[:300]
        out.append({"path": path, "why": why, "claim": text, "urls": [e.get("url") for e in node.get("evidence") or [] if e.get("url")][:3]})

    for path, node in walk(doc):
        if not isinstance(node, dict) or path.count(".evidence"):
            continue
        if path.startswith(".key_numbers["):
            add(path, node, "headline number")
        elif path.startswith(".company_card.economics.rows["):
            add(path, node, "public economics")
        elif path.startswith((".pricing_ladder.plans[", ".battlecard.price_compare[")):
            add(path, node, "price and billing basis")
        elif path.startswith(".passport.facts["):
            add(path, node, "passport fact")
    for path, node in walk(doc):
        if isinstance(node, dict) and node.get("evidence") and FRESH.search(" ".join(own_strings(node))):
            add(path, node, "F: deal, funding or leadership claim: open the newest primary source; it may be stale")
    for path, node in walk(doc):
        if isinstance(node, dict) and node.get("evidence") and re.search(r"\b(none|zero|never|no longer|removed|first|only|most|largest|leads?)\b",
                                                                      " ".join(own_strings(node)), re.I):
            add(path, node, "absolute or superlative wording: check the split it holds in")
    return out


def add_evidence(doc, issues, domains):
    """For each N flag, attach the collector item that contains the number and shares the most words with the claim."""
    items = []
    for d in domains:
        for f in (ROOT / "data" / d).glob("*.json"):
            if f.name.startswith("_") or f.name in ("analysis.json", "changes.json"):
                continue
            src = json.loads(f.read_text(encoding="utf-8"))
            items += [(f.stem, i) for i in src.get("items", []) if i.get("url")]
    nodes = dict(walk(doc))
    added = 0
    for path, code, msg in issues:
        if code != "N":
            continue
        m = re.search(r"number ([\d.]+)(k|m|%)?", msg)
        node = nodes.get(path)
        if not m or not isinstance(node, dict):
            continue
        v, suf = float(m.group(1)), m.group(2) or ""
        claim_words = set(re.findall(r"[a-z]{4,}", norm(" ".join(own_strings(node)))))
        best, score = None, 0
        for src, i in items:
            blob = norm(" ".join([i.get("text") or "", i.get("quote") or "", json.dumps(i.get("meta", {}))]))
            if not num_in(v, suf, blob):
                continue
            sc = len(claim_words & set(re.findall(r"[a-z]{4,}", blob)))
            if sc > score:
                best, score = (src, i), sc
        if best and score >= 2 and not any(e.get("url") == best[1]["url"] for e in node.get("evidence", [])):
            node.setdefault("evidence", []).append({"text": best[1].get("text", "")[:200], "quote": "", "url": best[1]["url"], "source": best[0]})
            added += 1
    return added


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--compare" in sys.argv:
        slug = "-vs-".join(d.split(".")[0] for d in args)
        f = ROOT / "data" / "_compare" / slug / "compare_analysis.json"
    else:
        f = ROOT / "data" / args[0] / "analysis.json"
    doc = json.loads(f.read_text(encoding="utf-8"))
    if "--targets" in sys.argv:
        t = targets(doc)
        (f.parent / "_factcheck_targets.json").write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding="utf-8")
        from collections import Counter
        print(f"targets: {len(t)} claims -> {f.parent / '_factcheck_targets.json'} " + str(dict(Counter(x["why"].split(":")[0] for x in t))))
        return
    issues = check(doc, args)
    if "--add-evidence" in sys.argv and any(c == "N" for _, c, _ in issues):
        added = add_evidence(doc, issues, args)
        f.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"add-evidence: attached {added} items (the LLM fact-check must confirm the meaning)")
        issues = check(doc, args)
    if "--fix-quotes" in sys.argv and any(c == "Q" for _, c, _ in issues):
        idx = collector_index(args)
        n = 0
        for path, node in walk(doc):
            for e in (node.get("evidence") or []) if isinstance(node, dict) else []:
                q = norm(e.get("quote"))
                if q and not any(q.rstrip(".") in norm(b) for b in idx.get(e.get("url"), [])):
                    e["quote"] = ""
                    n += 1
        f.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"fix-quotes: blanked {n} non-verbatim quotes")
        issues = check(doc, args)
    by = {}
    for p, c, msg in issues:
        by.setdefault(c, []).append((p, msg))
    for c in "QNWTD":
        for p, msg in by.get(c, [])[:40]:
            print(f"[{c}] {p}: {msg}")
    print(f"factcheck: {len(issues)} issues " + " ".join(f"{c}={len(by.get(c, []))}" for c in "QNWTD"))
    sys.exit(1 if issues else 0)


if __name__ == "__main__":
    main()
