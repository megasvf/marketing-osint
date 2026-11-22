# Dossier enrichment (opus, one company per agent)

Your final message IS the deliverable; finish, do not defer. Edit ONE file: `data/{domain}/analysis.json`. Load it with Python, assign the new keys, dump with `json.dump(a, f, ensure_ascii=False, indent=1)`. Write any helper script to a file with the Write tool and run it (no long Python in bash heredocs). Never change existing keys except `audience.segments[].level` (add) and `relationships` / `passport` / `pricing_ladder` / `for_me` (add or replace).

Inputs: the existing `analysis.json` (already fact-checked: reuse its wording and evidence), every collector file in `data/{domain}/*.json` (skip files starting with `_`). Reader profile (optional): `reader.json` or env `OSINT_READER` (see `reader.py`); without one, write `for_me` for a generic marketer ("you").

## Keys to add
```json
"relationships": {relationships},
"passport": {
  "tagline": "the company's own headline, verbatim from site.json",
  "facts": [{"label": "", "value": "", "evidence": [{"text": "", "quote": "", "url": "", "source": ""}]}]
},
"pricing_ladder": {
  "currency": "USD", "basis": "list price per month, billed monthly", "note": "what is excluded (usage fees, quote-only tiers)",
  "plans": [{"product": "", "plan": "", "price": 0, "price_yearly": 0, "unit": "per month", "seats": "", "note": "", "evidence": []}]
},
"for_me": {
  "verdict": "one sentence: why this company matters to the reader now",
  "by_relationship": {
    "<relationship>": {"summary": "one sentence", "points": [{"text": "", "action": "", "evidence": []}]}
  }
}
```
- `passport.facts`: exactly these labels in this order, each value ≤ 12 words: What it is · Products · Category · Founded · HQ · Ownership · Team size · Customers · Business model · Entry price · Sales motion · Financials. No source = value "not public" and `evidence: []`. Never guess a founding year, HQ or headcount. Team size = the company's own figure (or its parent's investor documents) plus the LinkedIn member count from `linkedin.json` (people who list the company as employer; a proxy, not an exact headcount). HQ = the legal entity and city, plus where most staff sit when an investor document gives a split, plus the parent company and its city when the company is owned by a group (`linkedin.json` parent item, corporate releases). Read the about page and the site footer first (legal entity + city, launch year), and WebFetch them if site.json lacks them (append the item). Customer counts only from the company or its parent's own pages / releases, never from AI summaries alone. Financials: quote the exact figure, never "above" a rounded one.
- `pricing_ladder.plans`: every public self-serve and SDK / plugin plan, cheapest first, within each product. `price` = monthly list price billed monthly as a number (0 for free); `price_yearly` = per-month price when billed yearly, or null. Take both from the `monthly` and `yearly` modes of `pricing.json` when present (never put a yearly-billed price in `price`). Quote-only plans: `price` null and note "quote only". Prices must match the pricing page in `site.json` / `wayback.json` exactly. Seats / users / units come from the live pricing matrix (fetch it), never from third-party reviews; vendors price on different units (users, unique emails, API calls), so never call one tier "cheaper" without saying the units differ. Reader prices (price checks) come from the reader profile only.
- `audience.segments[].level`: "primary" (headline or most ad/page effort), "secondary" (dedicated page or offer) or "emerging" (new in the last 6 months or a single signal). Base it on the segment's existing `signal` text.
- `for_me.by_relationship`: one entry per value in `relationships`, 3 points each, every point = text (what we saw, ≤ 30 words) + action (what the reader's marketing does, ≤ 20 words, inside one unit's ownership) + 1-2 evidence items. Derive points from the existing `battlecard`, `lens_block`, `so_what`, `department_briefs` and `swot`; do not invent new facts.
  - competitor: where we win, where we lose, what to answer.
  - benchmark: tactics worth borrowing (format, channel, offer, page pattern).
  - self: what the outside view says we should fix or double down on. Never print the reader's private figures; the public one stands.
  - The verdict may only restate what the points show; a branded/non-branded claim needs a split that isolates it.
  - prospect (the company could buy from the reader): also add `"fit": [{"criterion", "verdict": "yes|partly|no|unknown", "text", "evidence"}]` (4-6 criteria from the reader profile's `ideal_customer`; without a profile: team size, industry, tools in use, budget signals), `"buyers": [{"role", "why"}]` (roles only, never names), `"pains": [{"text", "evidence"}]` (pains visible from outside that the reader's product addresses: job posts, review complaints, inconsistent pages), `"angle": {"text"}` (one way in for sales).
  - partner (integration, co-marketing, affiliate): also add `"overlap": [{"text", "evidence"}]` (shared audience), `"ideas": [{"title", "body", "unit"}]` (joint actions, owning reader unit), `"risks": [{"text"}]`. Apply the reader profile's `rules`.

## Hard rules
- Every evidence `url` is copied exactly from a collector item in `data/{domain}/` (no invented URLs); `quote` is verbatim page text ≤ 25 words or "".
- Every number in a text or value appears in a cited collector item (±1.5%).
- Plain English, no hype words, no em dashes (use commas, colons, parentheses), no intent-implying tone ("aims to", "wants to").
- Then run `python factcheck.py {domain} --add-evidence --fix-quotes` and `python factcheck.py {domain}` from the repo root; fix the analysis until it prints `0 issues`. Also run `python build.py {domain}`: it must print `lint ok`.

Final message: the passport facts table (label, value, cited yes/no), the pricing ladder rows, segment levels, the for_me verdict and point titles, and the gate + lint output.
