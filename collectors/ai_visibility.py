"""Collector 9b — AI visibility: the same buyer prompts asked to several LLMs with web search.

Measures: is the brand mentioned, its rank in the answer's list, which brands appear next to it,
which domains the model cites. Raw answers go to data/<domain>/_ai_raw.json and are published as
ai_answers.html next to the report, so every number has a readable source.

Keys from env: OPENAI_API_KEY, GEMINI_API_KEY, XAI_API_KEY (a missing key = that model skipped).
Models via env OSINT_OPENAI_MODEL / OSINT_GEMINI_MODEL / OSINT_XAI_MODEL.

Usage: python collectors/ai_visibility.py example.com --brand Example --alt "Old Name" --category "form builder"
       [--competitor Rival --competitor Other ...]
"""
import argparse
import json
import os
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import requests

from common import ROOT, write_source

import sys as _sys
_sys.path.insert(0, str(ROOT))
import costs  # noqa: E402

MODELS = {
    "openai": os.environ.get("OSINT_OPENAI_MODEL", "gpt-5.5"),
    "gemini": os.environ.get("OSINT_GEMINI_MODEL", "gemini-3.8-flash"),
    "xai": os.environ.get("OSINT_XAI_MODEL", "grok-4.7"),
}
PROMPTS = [
    "What are the best {category} tools right now? Give a ranked list with one line on each.",
    "Which {category} should a small marketing team pick? Rank the top options.",
    "Best {category} for agencies managing many clients? Ranked list please.",
    "Best {category} for large enterprise teams? Ranked list please.",
    "What is the best free {category}? Rank the options.",
    "Which {category} has the best integrations with the other tools a team already uses? Rank the top options.",
    "What is {brand} and what is it best known for?",
    "What are the main pros and cons of {brand}?",
    "What are the best alternatives to {brand}? Ranked list.",
    "Is {brand} worth paying for compared with other {category} tools?",
]


def ask_openai(prompt):
    r = requests.post("https://api.openai.com/v1/responses", timeout=120,
                      headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
                      json={"model": MODELS["openai"], "input": prompt, "tools": [{"type": "web_search"}]})
    r.raise_for_status()
    d = r.json()
    text, cites = "", []
    for o in d.get("output", []):
        for c in o.get("content", []) or []:
            if c.get("type") == "output_text":
                text += c.get("text", "")
                cites += [a.get("url") for a in c.get("annotations", []) if a.get("url")]
    return text, cites, d.get("usage", {})


def ask_gemini(prompt):
    m = MODELS["gemini"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"
    hdr = {"x-goog-api-key": os.environ["GEMINI_API_KEY"]}
    body = {"contents": [{"parts": [{"text": prompt}]}], "tools": [{"google_search": {}}]}
    r = requests.post(url, headers=hdr, json=body, timeout=120)
    search = True
    if r.status_code == 429 and "quota" in r.text.lower():  # grounding quota exhausted: answer without search
        body.pop("tools")
        search = False
        r = requests.post(url, headers=hdr, json=body, timeout=120)
    elif r.status_code == 429:  # rate limit: one short back-off
        time.sleep(15)
        r = requests.post(url, headers=hdr, json=body, timeout=120)
    r.raise_for_status()
    d = r.json()
    cand = (d.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
    chunks = cand.get("groundingMetadata", {}).get("groundingChunks", [])
    # grounding uris are vertexaisearch redirects; the chunk title carries the source domain
    cites = [c.get("web", {}).get("title") or c.get("web", {}).get("uri") for c in chunks if c.get("web")]
    usage = d.get("usageMetadata", {})
    if not search:
        usage["note"] = "no web search (grounding quota exhausted)"
    return text, cites, usage


def ask_xai(prompt):
    h = {"Authorization": f"Bearer {os.environ['XAI_API_KEY']}"}
    body = {"model": MODELS["xai"], "input": prompt, "tools": [{"type": "web_search"}]}
    r = requests.post("https://api.x.ai/v1/responses", headers=h, json=body, timeout=180)
    if r.status_code >= 400:  # fall back to plain chat (no live search)
        r = requests.post("https://api.x.ai/v1/chat/completions", headers=h, timeout=180,
                          json={"model": MODELS["xai"], "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status()
        d = r.json()
        return d["choices"][0]["message"]["content"], d.get("citations", []), {"note": "no web search"}
    d = r.json()
    text, cites = "", []
    for o in d.get("output", []):
        for c in o.get("content", []) or []:
            if c.get("type") == "output_text":
                text += c.get("text", "")
                cites += [a.get("url") for a in c.get("annotations", []) if a.get("url")]
    return text, cites + d.get("citations", []), d.get("usage", {})


ASK = {"openai": ask_openai, "gemini": ask_gemini, "xai": ask_xai}
KEYS = {"openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY", "xai": "XAI_API_KEY"}


STOP = {"how", "my", "why", "need", "already", "default", "ranked", "custom", "best", "option", "options",
        "recommendation", "scenario", "choose", "pros", "cons", "summary", "verdict", "bottom", "pricing",
        "if", "for", "what", "when", "use", "quick", "top", "final", "overall", "short", "key", "budget",
        "free", "paid", "pick", "decision", "rule", "the", "a", "note", "notes", "tip", "tips", "honorable", "also", "other"}


def list_names(text):
    """Leading names of numbered/bulleted/heading lines = the answer's ranked list (product names only)."""
    names = []
    for line in text.splitlines():
        m = re.match(r"\s*(?:\d+[.)]|[-*•]|#{2,4})\s+(?:\*\*)?([A-Z0-9][\w.&+'/ -]{1,40}?)(?:\*\*)?"
                     r"\s*(?:[:(–—-]|\*\*|$)", line)
        if not m:
            continue
        n = m.group(1).strip(" *.")
        words = n.split()
        if not (1 < len(n) <= 40 and len(words) <= 4) or words[0].lower() in STOP:
            continue
        names.append(n)
    return list(dict.fromkeys(names))


RANK_ROW = [re.compile(r"^\s*\|\s*\**\s*#?(\d{1,2})\s*\**\s*\|\s*(.+?)\s*\|"),          # | 1 | Name | ... |
            re.compile(r"^\s*(?:#{1,4}\s*)?\**(\d{1,2})[.)]\**\s+(.{1,80})")]               # 1. Name / ### 2) Name


def ranked_list(text):
    """The answer's own first ranked list or table: [(rank, entry text)], from its '1' until the numbering restarts."""
    rows, started = [], False
    for line in text.splitlines():
        m = next((m for rx in RANK_ROW if (m := rx.match(line))), None)
        if not m:
            continue
        n = int(m.group(1))
        if n == 1 and started:
            break
        if n == 1:
            started = True
        if started:
            rows.append((n, m.group(2).replace("*", "").strip()))
    return rows


def answer_rank(text, rx):
    """(rank in the answer's own list or None, list length, status) where status is ranked | named_outside_list | no_list."""
    rows = ranked_list(text)
    if not rows:
        return None, 0, "no_list"
    hit = next((n for n, entry in rows if rx.search(entry[:60])), None)
    return hit, len(rows), ("ranked" if hit else "named_outside_list")


SECOND_LEVEL = {"co", "com", "org", "net", "ac", "gov", "edu", "ne", "or"}  # co.uk, com.au, co.jp ...


def site_of(host):
    """Registrable site of a host: support.atlassian.com -> atlassian.com, blog.example.co.uk -> example.co.uk."""
    parts = host.lower().strip(".").split(".")
    if len(parts) >= 3 and parts[-2] in SECOND_LEVEL and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def mention_rx(terms):
    return re.compile(r"\b(" + "|".join(re.escape(t) for t in terms) + r")\b", re.I)


def run_one(provider, idx, prompt):
    t0 = time.time()
    try:
        text, cites, usage = ASK[provider](prompt)
        return {"provider": provider, "model": MODELS[provider], "idx": idx, "prompt": prompt, "text": text,
                "cites": [c for c in cites if c], "usage": usage, "secs": round(time.time() - t0, 1)}
    except Exception as e:  # keep the error (secrets scrubbed), never invent an answer
        err = re.sub(r"(key|token)=[^&\s]+", r"\1=[redacted]", str(e))[:300]
        return {"provider": provider, "model": MODELS[provider], "idx": idx, "prompt": prompt,
                "error": err, "secs": round(time.time() - t0, 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("domain")
    ap.add_argument("--brand", required=True)
    ap.add_argument("--alt", action="append", default=[])
    ap.add_argument("--category", required=True)
    ap.add_argument("--competitor", action="append", default=[])
    ap.add_argument("--retry-failed", action="store_true", help="re-ask only failed (model, prompt) pairs, keep the rest")
    ap.add_argument("--skip", action="append", default=[], help="provider to skip, e.g. xai (no credits)")
    a = ap.parse_args()
    providers = [p for p in ASK if os.environ.get(KEYS[p]) and p not in a.skip]
    prompts = [p.format(category=a.category, brand=a.brand) for p in PROMPTS]
    raw_f = ROOT / "data" / a.domain / "_ai_raw.json"
    prev = json.loads(raw_f.read_text(encoding="utf-8")) if a.retry_failed and raw_f.exists() else []
    keep = {(r["provider"], r["idx"]): r for r in prev if not r.get("error")}

    def run_provider(p):
        todo = [(i, q) for i, q in enumerate(prompts) if (p, i) not in keep]
        workers = 1 if p == "gemini" else 4
        with ThreadPoolExecutor(max_workers=workers) as ex:
            return list(ex.map(lambda iq: run_one(p, *iq), todo))
    with ThreadPoolExecutor(max_workers=len(providers) or 1) as ex:
        fresh = [r for rows in ex.map(run_provider, providers) for r in rows]
    merged = {**{(r["provider"], r["idx"]): r for r in prev}, **keep, **{(r["provider"], r["idx"]): r for r in fresh}}
    raw = sorted(merged.values(), key=lambda r: (r["provider"], r["idx"]))
    providers = sorted({r["provider"] for r in raw})
    raw_f.write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
    tool = {"openai": "OpenAI API", "gemini": "Gemini API", "xai": "xAI API"}
    for p in sorted({r["provider"] for r in fresh}):
        rows = [r for r in fresh if r["provider"] == p]
        ok = [r for r in rows if not r.get("error")]
        tin = sum((r.get("usage") or {}).get("input_tokens", 0) or (r.get("usage") or {}).get("promptTokenCount", 0) for r in ok)
        tout = sum((r.get("usage") or {}).get("output_tokens", 0) or (r.get("usage") or {}).get("candidatesTokenCount", 0) for r in ok)
        note = f"{MODELS[p]}: {len(ok)} answered, {len(rows) - len(ok)} failed; {tin:,} input + {tout:,} output tokens"
        if p == "openai" and ok:
            note += "; web search tool fees apply per call"
        costs.record(a.domain, tool[p], len(ok), "calls", note)

    brand_rx = mention_rx([a.brand] + a.alt + [a.domain])
    items, co = [], Counter()
    sov = {p: [0, 0] for p in providers}
    cited, cited_bl = Counter(), Counter()
    # candidate brand set = list leaders from every answer + --competitor names, shortened to the core name
    cands = Counter()
    for r in raw:
        if not r.get("error"):
            cands.update(re.split(r"\s*[/(]\s*", n)[0].strip() for n in list_names(r["text"]))
    generic = {"esp", "esps", "html", "amp", "css", "sdk", "api", "crm", "sms", "ai", "ui", "ux", "seo", "saas", "b2b", "b2c",
               "you", "shortlist", "white", "yes", "no", "option", "choose", "start", "use", "go", "skip", "avoid", "consider",
               "email", "emails", "builder", "templates", "template", "editor", "tool", "tools", "file", "files",
               "most", "mac", "macos", "windows", "linux", "ios", "android", "web", "desktop", "mobile", "teams"}
    raw_names = [c for c in dict.fromkeys(a.competitor + [c for c, _ in cands.most_common()])
                 if len(c) > 2 and not brand_rx.search(c) and c.split()[0].lower().strip(".:") not in generic | STOP]
    # a heading word ("Databases", "Open", "Integrations") is used lowercase in running text; brand names are not
    texts = " ".join(r["text"] for r in raw if not r.get("error"))
    def generic_word(c):
        low = len(re.findall(r"(?<![\w.])" + re.escape(c.lower()) + r"(?![\w])", texts))
        cap = len(re.findall(r"(?<![\w.])" + re.escape(c) + r"(?![\w])", texts))
        return c not in a.competitor and low >= max(1, cap // 2)
    raw_names = [c for c in raw_names if not generic_word(c)]
    cand_names = []
    for c in sorted(raw_names, key=len):  # merge 'Acme.io' into 'Acme', 'Acme Plugin' into 'Acme'
        if not any(re.match(re.escape(k) + r"(\W|$)", c, re.I) for k in cand_names):
            cand_names.append(c)
    cand_rx = {c: re.compile(r"(?<!\w)" + re.escape(c) + r"(?!\w)", re.I) for c in cand_names}

    def mention_order(text):
        """Brands ordered by first mention in the answer (the subject brand included)."""
        pos = {c: m.start() for c, rx in cand_rx.items() if (m := rx.search(text))}
        if (m := brand_rx.search(text)):
            pos[a.brand] = m.start()
        return [c for c, _ in sorted(pos.items(), key=lambda kv: kv[1])]

    for r in raw:
        anchor = f"ai_answers.html#{r['provider']}-{r['idx']}"
        if r.get("error"):
            continue
        text = r["text"]
        order = mention_order(text)
        names = order
        hit = bool(brand_rx.search(text))
        morder = order.index(a.brand) + 1 if a.brand in order else None
        rank, n_list, rstat = answer_rank(text, brand_rx) if hit else (None, len(ranked_list(text)), "not_mentioned")
        sov[r["provider"]][1] += 1
        sov[r["provider"]][0] += hit
        brandless = r["idx"] < 6  # prompts that do not name the brand
        if brandless:
            co.update(c for c in order if c != a.brand)  # answers mentioning each brand anywhere
        for c in r["cites"]:
            host = urlparse(c).netloc.replace("www.", "") if c.startswith("http") else c
            site = site_of(host) if "." in host else host
            cited[site] += 1
            if brandless:
                cited_bl[site] += 1
        sent = next((s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if brand_rx.search(s)), "")
        items.append({"type": "ai_answer",
                      "text": f"{r['model']}: {'mentions' if hit else 'does not mention'} {a.brand}"
                              + ({"ranked": f" (#{rank} of {n_list} in the answer's own list)",
                                  "named_outside_list": " (named, but not in the answer's ranked list)",
                                  "no_list": " (the answer has no ranked list)"}.get(rstat, "")) + f" for: {r['prompt'][:80]}",
                      "quote": " ".join(sent.split()[:25]), "url": anchor,
                      "meta": {"provider": r["provider"], "model": r["model"], "prompt_idx": r["idx"],
                               "brand_named_in_prompt": not brandless, "mentioned": hit, "rank": rank,
                               "rank_status": rstat, "list_len": n_list, "mention_order": morder,
                               "list": names[:12], "n_cites": len(r["cites"]),
                               "web_search": "no web search" not in json.dumps(r.get("usage", {}))}})
    # brandless share of voice = the honest visibility number (only models that answered)
    answered = sorted({r["provider"] for r in raw if not r.get("error")})
    for p in answered:
        rows = [i for i in items if i["meta"]["provider"] == p and not i["meta"]["brand_named_in_prompt"]]
        hits = sum(i["meta"]["mentioned"] for i in rows)
        ranks = [i["meta"]["rank"] for i in rows if i["meta"]["rank"]]
        first = sum(1 for x in ranks if x == 1)
        outside = sum(1 for i in rows if i["meta"]["rank_status"] == "named_outside_list")
        items.append({"type": "metric", "text": f"{MODELS[p]}: {a.brand} appears in {hits} of {len(rows)} category prompts; "
                      f"first in {first} of the answers' own ranked lists" + (f", named outside the list in {outside}" if outside else ""),
                      "url": f"ai_answers.html#{p}", "meta": {"provider": p, "hits": hits, "of": len(rows), "first": first,
                                                           "ranks": ranks, "named_outside_list": outside,
                                                           "avg_rank": round(sum(ranks) / len(ranks), 1) if ranks else None}})
    items.append({"type": "metric", "text": "Brands named most often in category answers: "
                  + ", ".join(f"{n} {c}" for n, c in co.most_common(10)),
                  "url": "ai_answers.html", "meta": {"co_mentions": co.most_common(20)}})
    if cited:
        items.append({"type": "metric", "text": f"Most cited sites (subdomains grouped), all {len(prompts)} prompts (incl. those naming {a.brand}): "
                      + ", ".join(f"{h} {c}" for h, c in cited.most_common(10)),
                      "url": "ai_answers.html", "meta": {"cited": cited.most_common(25), "scope": "all prompts"}})
    if cited_bl:
        items.append({"type": "metric", "text": "Most cited sites (subdomains grouped), the 6 category prompts that do not name the brand: "
                      + ", ".join(f"{h} {c}" for h, c in cited_bl.most_common(10)),
                      "url": "ai_answers.html", "meta": {"cited": cited_bl.most_common(25), "scope": "brandless prompts"}})
    errs = [r for r in raw if r.get("error")]
    failed = {}
    for r in errs:
        failed.setdefault(r["model"], r["error"].split(" for url")[0][:80])
    status = "ok" if answered and not errs else ("partial" if answered else "unavailable")
    note = (f"answered: {[MODELS[p] for p in answered]}, {len(prompts)} prompts each; prompts 1-6 do not name the brand"
            + ("; failed: " + "; ".join(f"{m} ({e})" for m, e in failed.items()) if failed else ""))
    write_source(a.domain, "ai_visibility", status, items, note)


if __name__ == "__main__":
    main()
