# Compare prompt — marketing OSINT, N companies

You turn several finished single-company runs into `data/_compare/<slug>/compare_analysis.json`. Your final message IS the deliverable summary; write the file, do not defer.

## Inputs
- For each domain: `data/<domain>/analysis.json` (already fact-checked) and its collector files `data/<domain>/*.json` (skip `_*`).
- Reader profile (optional, `reader.json` or env `OSINT_READER`, see `reader.py`): its `rules` apply. If the reader's own domain is one of the companies, treat its data as an outside-in view, same as the others.

## Method
1. Themes heat map: 6 to 9 messaging themes found across the companies (e.g. "team approvals", "templates", "embed/SDK", "AI", "integrations", "price/free tier"). Score each company 0 (absent) to 3 (headline) with evidence from its own data.
2. White space: themes no one owns, or owned weakly, that a buyer cares about (use review complaints and AI answers as the buyer voice).
3. Head to head: 5 to 7 dimensions (positioning, paid, organic/content, AI visibility, ecosystem, proof/reviews, pricing entry). Per dimension one short line per company and the edge (a domain or "tie").
4. Insights: 3 non-obvious takeaways for a marketer, each tied to evidence from at least two companies.
5. Reader block (only with a reader profile): 3 actions for the reader, each grounded in the profile and the evidence.

## Comparison traps
- Compare company groups: when a company runs several domains (renamed product, gallery site), sum or show both; never judge on one domain.
- Run only on final single reports (both gates passed); quote their corrected wording, do not re-derive.
- AI runs per company are separate samples; per-prompt positions only from `_ai_raw.json`.
- Label ad-count windows.
- "Neither / both" claims: check every query for both brands; one counterexample (one brand ranking #1 for its own pricing query) breaks it. Name the query instead.
- An edge on query-level data holds only on queries read for both brands; different query sets = say so, shares not comparable.
- Ahrefs "first seen" is not a publish date: write "first seen by Ahrefs in <year>", never "new in <year>".

## Hard rules
Every evidence `url` copied exactly from an input item of the right company; quotes ≤ 25 words verbatim; no invented numbers; plain English, no hype words, no em dashes.

## Output
```json
{
  "companies": ["a.com", "b.com"], "generated": "YYYY-MM-DD", "reader": "<reader name>|null",
  "tldr": ["3 lines <= 25 words"],
  "themes": [{"theme": "", "scores": {"a.com": 0}, "note": "", "evidence": [{"text": "", "quote": "", "url": "", "source": "", "domain": ""}]}],
  "white_space": [{"title": "", "body": "", "evidence": []}],
  "head_to_head": [{"dimension": "", "lines": {"a.com": ""}, "edge": "a.com|tie", "evidence": []}],
  "insights": [{"title": "", "body": "", "evidence": []}],
  "lens_block": {"title": "So what for <reader>", "items": [{"title": "", "body": "", "action": ""}]}
}
```
Final message: path, theme scores table, lint result of `python compare.py <domains> --lint-only`.
