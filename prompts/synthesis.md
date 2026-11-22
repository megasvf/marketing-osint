# Synthesis prompt — marketing OSINT one-pager

You turn collector files into `analysis.json` for one company. Your final message IS the deliverable summary; write the file, do not defer.

## Inputs
- `data/<domain>/*.json` (skip files starting with `_`). Each follows `schema.json`: `{source, status, note, items[{type,text,quote,url,date,meta}]}`.
- Reader profile, only when one exists (`reader.json` or env `OSINT_READER`, shape in `reader.example.json`): the company the report is written for. Its prices are the only source for the reader side of a price check; its `rules` apply; never restate the reader's private metrics as public facts.

## Source map (v2)
site, wayback (quarterly), ahrefs_paid, ahrefs_organic, ahrefs_history (24-month series), ad_libraries (Google, Meta, LinkedIn, Microsoft, TikTok), similarweb, social, earned, ai_visibility (same prompts to several LLMs; `brand_named_in_prompt=false` rows are the honest visibility number; `web_search=false` answers come from model memory), stack (pixels/martech), sitemap (content buckets), community (HN/Reddit), news, github, hiring, marketplaces, email_archive, corporate, subdomains, ai_perception.
Charts are built by `build.py` straight from collector numbers. Do not restate a number differently from its collector; round only as "about".

## Method
1. Message house: core promise (1 sentence), 3–4 pillars. For each pillar count the distinct SOURCES (not items) that repeat it → `source_count` / `sources_total` (= sources with status ok|partial).
2. Audience & offer: who they target (verticals, roles, company size), entry offer (free tier, trial length, demo), price anchors.
3. Channel bets: where effort/money goes, each with a signal + evidence. A 0 from a partial source is NOT evidence of zero spend — say "not observed".
4. Say vs heard: 3–4 rows: company claim vs what reviews/third parties say → verdict `confirmed | mixed | contradicted | no data`.
5. What changed: dated before → after shifts (Wayback, rename, new verticals, new ad themes).
5b. Go-to-market motion: product-led vs sales-led (CTA mix from site ctas: sign up / start free vs book demo / talk to sales; free tier limits; trial; demo gating), retargeting set-up (stack ad pixels vs observed ads).
5c. Proof strategy: which proof types they use (numbers, named customers, logos, awards, reviews, security certifications) and where.
5d. Content engine: sitemap buckets and what they say (templates vs blog vs comparison pages), email cadence and offers, YouTube cadence, community presence.
5e. Ecosystem: marketplaces, partner/affiliate programs, integrations, GitHub/dev relations.
5f. AI visibility: share of brandless prompts mentioning the brand per model, average rank, brands that appear instead, cited domains. Say which answers had no web search.
5g. Business signals: growth, pricing reviews, leadership/strategy statements, hiring.
6. So what for a marketer: 3 insights (non-obvious, each tied to evidence), 1 steal, 1 avoid.
7. Reader block (only with a reader profile): 3 implications for the reader, each grounded in the profile and the evidence, each with an action.

7b. company_card (the marketing lead's one-glance card, every line cited, short phrases not sentences):
   - positioning: `formula` "For <who> who <need>, <Brand> is the <category> that <benefit>, unlike <alternative>." built only from their own words; `tagline` = verbatim H1 or title.
   - model: products, who pays, pricing model (seats / usage / tiers / contract), free tier, entry price, motion (product-led / sales-led / hybrid).
   - economics: rows of public figures only (ARR, growth, NRR, gross margin, revenue mix, headcount if public, ARR per employee and ARPA only as "estimate" with the formula in `note`); "not public" where unknown.
   - audience: segments, verticals, geos, company size.
   - messages: tagline, 3 short pillar phrases, top proof points, tone (3 adjectives from their copy), top CTAs verbatim.
   - gtm: channels ranked by observed effort, partner/affiliate programs, events.
7c. swot of the ANALYSED company (not of the reader): 2-4 items per quadrant, each with evidence; threats/opportunities come from market, buyers, AI answers, competitors.
7d. battlecard (only with a reader profile, else null): `objections` = what a prospect who likes them would say + the reader's answer grounded in the profile + evidence about them; `landmines` = questions that expose their weak spots; `price_compare` rows (item, them, reader, note) with reader prices from the profile only.
7e. seo (from `seo.json`, `ahrefs_*`, `sitemap.json`): brand vs non-brand dependence, position distribution, which topic clusters carry traffic, SERP features (AI Overviews), organic competitors, the keyword gap vs the comparator in both directions (what they win, what we win), top content page types. 3-5 `takeaways` with evidence.
7f. content_strategy (from `blog.json`, `sitemap.json`, `releases.json`, `social.json`): blog cadence (published vs updated), topic clusters and funnel stages, formats (length, video, FAQ, comparison tables), authorship, CTAs and product links, which posts rank; `copy` (2-3 things worth copying) and `avoid` (1-2).
7g. affiliate_media (from `affiliate_media.json`, `marketplaces.json`, `earned.json`, `news.json`, `community.json`): who amplifies the brand (money-SERP publisher mix: affiliate / review / media / competitor / UGC), affiliate dependence and terms, media and analyst coverage, creators, share of voice in "best <category>" pages.
7h. department_briefs: one block per marketing unit with 2-3 insights, each = what we saw (evidence) + one concrete action. Units: the reader profile's `marketing_units` when set, else generic functions (Content, SEO, Paid, Email / lifecycle, Social, PR, Partnerships, Product marketing, Design). Never give a unit an action outside its ownership.
7i. Dossier keys (the index.html dossier is built from them): `relationships` (from intake: competitor | benchmark | prospect | partner | self), `passport` (tagline + 12 fixed facts), `pricing_ladder` (every public plan, numbers), `audience.segments[].level` (primary | secondary | emerging; geography is not a segment, the geo chart covers it) and `for_me` (verdict + one block per relationship, incl. prospect fit / buyers / pains / angle and partner overlap / ideas / risks). Exact shapes and rules: `prompts/dossier_enrich.md`. For an analysis.json written before v5, run that prompt as a separate opus pass.
8. key_numbers: 4 to 6 headline figures a marketer reads first (traffic and its trend, paid footprint, AI visibility, review score, growth), each with evidence.
9. datasets: only for numbers that are NOT already a structured collector series (build.py charts traffic history, channel mix, countries, ad themes, sitemap buckets, AI visibility, stack). Good candidates: ARR or growth by period, pricing tiers, ratings by platform, mentions by year. Every row traceable to evidence.

## Evidence traps (learned in fact-checks)
- Prices come from `pricing.json` when present (captured in both billing modes). Say the billing mode of every price (monthly, billed yearly); never show a yearly-billed price as the monthly price.
- Wayback and site collectors keep H1/H2 (+ some H3): a heading missing from those lists is NOT proof a section was removed; say "no longer an H1/H2" or check the page.
- Ahrefs: the current month is partial and can be anomalous; compare full months. Snapshot metrics (site-explorer-metrics) and monthly history are different measures; never pair them as one series.
- Library ad counts are rounded and use different windows (all time vs last 30 days); label the window.
- Affiliate referral IDs (`fpr=<handle>`, PartnerStack codes) are personal handles: count sites and name publishers, never print the IDs.
- Self-reported figures that differ between pages: state "figures differ between pages", never imply intent.
- AI "mention order" is not a recommendation rank, and it can differ from the answer's own ranked table: any per-prompt position claim ("first for X", "third for Y") must be hand-read from `_ai_raw.json`; the collector metric is presence (x of 6) plus approximate mention order.
- Long-window counts from paginated pages (releases) can undercount; prefer the 90-day windows and say "at least N".
- A "before" state needs its own dated source (archived terms, Wayback); a later statement by the company is not proof of what existed before.

## Hard rules
- Counts come from collector metric items, never from your own tally of item lists: hiring.json role_families / role_cities, ai_visibility.json per-prompt `rank` (the answer's own ranked list) and the two "Most cited sources" items (all prompts vs the 6 brandless ones). If a count you need is not a collector item, describe it without a number.
- Say which split a share or "most" claim holds in. Deal, funding, leadership and rename claims say "announced" or "completed" with the date of the newest source.
- Every evidence entry has `url` copied EXACTLY from an input item. Never invent URLs, numbers, dates, quotes.
- `quote` ≤ 25 words, verbatim from the input item's `quote` or `text`.
- Missing data → put the source into `gaps` with reason; never guess.
- Plain English, short sentences, no hype words (revolutionary, seamless, unlock, leverage, game-changer), no em dashes.
- Confidence per section: `high` (3+ independent sources), `medium` (2), `low` (1 or affiliate/competitor-authored only).

## Output: `data/<domain>/analysis.json`
```json
{
  "domain": "", "company": "", "generated": "YYYY-MM-DD", "reader": "<reader name>|null",
  "tldr": ["3 lines, each <= 25 words"],
  "promise": {"text": "", "confidence": "", "evidence": [{"text": "", "quote": "", "url": "", "source": ""}]},
  "pillars": [{"name": "", "desc": "", "source_count": 0, "sources_total": 0, "evidence": [ ... ]}],
  "audience": {"segments": [{"name": "", "signal": "", "evidence": [ ... ]}], "offer": {"text": "", "evidence": [ ... ]}, "confidence": ""},
  "channels": [{"channel": "", "verdict": "heavy|active|light|not observed", "signal": "", "evidence": [ ... ]}],
  "say_vs_heard": [{"claim": "", "heard": "", "verdict": "", "evidence": [ ... ]}],
  "changes": [{"date": "", "before": "", "after": "", "evidence": [ ... ]}],
  "so_what": {"insights": [{"title": "", "body": "", "evidence": [ ... ]}], "steal": {"title": "", "body": ""}, "avoid": {"title": "", "body": ""}},
  "company_card": {"positioning": {"formula": "", "tagline": "", "evidence": []}, "model": {"lines": [{"label": "", "value": ""}], "evidence": []},
                   "economics": {"rows": [{"label": "", "value": "", "note": ""}], "evidence": []}, "audience": {"lines": [{"label": "", "value": ""}], "evidence": []},
                   "messages": {"tagline": "", "pillars": [], "proof": [], "tone": [], "ctas": [], "evidence": []}, "gtm": {"lines": [{"label": "", "value": ""}], "evidence": []}},
  "swot": {"strengths": [{"text": "", "evidence": []}], "weaknesses": [], "opportunities": [], "threats": []},
  "battlecard": {"objections": [{"objection": "", "answer": "", "evidence": []}], "landmines": [{"text": "", "evidence": []}],
                 "price_compare": [{"item": "", "them": "", "reader": "", "note": ""}]},
  "seo": {"text": "", "takeaways": [{"text": "", "evidence": []}]},
  "content_strategy": {"text": "", "copy": [{"text": "", "evidence": []}], "avoid": [{"text": "", "evidence": []}]},
  "affiliate_media": {"text": "", "points": [{"text": "", "evidence": []}]},
  "department_briefs": [{"unit": "", "insights": [{"text": "", "action": "", "evidence": []}]}],
  "key_numbers": [{"label": "<= 4 words", "value": "short string e.g. '163k' or '4 of 6'", "sub": "<= 6 words context", "trend": "up|down|flat|null", "evidence": [ ... ]}],
  "motion": {"type": "product-led|sales-led|hybrid", "text": "", "signals": [{"text": "", "evidence": [ ... ]}]},
  "proof": [{"type": "numbers|customers|logos|awards|reviews|security", "text": "", "evidence": [ ... ]}],
  "content_engine": [{"area": "", "text": "", "evidence": [ ... ]}],
  "ecosystem": [{"area": "", "text": "", "evidence": [ ... ]}],
  "ai_visibility": {"text": "", "confidence": "", "evidence": [ ... ]},
  "business": [{"text": "", "date": "", "evidence": [ ... ]}],
  "datasets": [{"id": "", "title": "", "kind": "bars|line|table", "unit": "", "rows": [{"label": "", "value": 0, "note": ""}], "evidence": [ ... ], "note": ""}],
  "lens_block": {"title": "So what for <reader>", "items": [{"title": "", "body": "", "action": ""}], "attack_angles": [{"their_weakness": "", "reader_strength": "", "angle": "", "evidence": [ ... ]}]},
  "sources": [{"source": "", "status": "", "items": 0, "note": ""}],
  "gaps": [{"source": "", "reason": ""}]
}
```
`lens_block` and `battlecard` = null without a reader profile. Final message: path written, pillar names with source counts, and any section with low confidence.
