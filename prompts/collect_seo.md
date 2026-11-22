# Collector prompt — SEO deep dive (haiku or sonnet, background, Ahrefs)

Placeholders: {domain}, {siblings}, {brand}, {comparator} (the reader's domain from the reader profile for a gap; with no reader profile or for the reader's own report, the main competitor).
Your final message IS the deliverable; finish, do not defer.

**BUDGET (hard):** Ahrefs units are a shared monthly quota. Max 12 Ahrefs calls and ≈ 15k units per company. organic-keywords costs per row: use limit ≤ 100 per call (never 250-row pages), at most 2 calls per domain. NO per-keyword lookups for the gap: compute the gap only from the two top-keyword lists you already pulled (a keyword absent from the other list = "not in its top N"). Check `subscription-info-limits-and-usage` after the 4th call; stop and report if units used > 15k. One SEO agent at a time.

Ahrefs MCP (ToolSearch, tool names contain `Ahrefs` or the Ahrefs server name); `doc` before first use; money in USD cents; no render tools. Units before/after → `python costs.py {domain} "Ahrefs API" <units> units "SEO deep dive"` (run in the repo root). Rows ≤ 100 per call (cost scales with rows); country = us for competitors/gap. Mode = subdomains.

Write `data/{domain}/seo.json` (contract `schema.json`, source "seo"; text ≤ 40 words, no em dashes; url REQUIRED: the ranking page URL, or the Ahrefs overview URL `https://app.ahrefs.com/site-explorer/overview/v2/subdomains/live?target={domain}` for aggregates):
1. **Brand vs non-brand**: share of organic traffic and keywords that are branded (`is_branded`), from organic-keywords (top 500 by traffic, aggregate locally). One metric item.
2. **Position distribution**: keywords in top 3 / 4-10 / 11-20 / 21-50 (metrics or keywords history latest point). One metric item, meta {top3, top4_10, top11_20, top21_50}.
3. **Topic clusters**: group the top 300 non-branded keywords by intent cluster (templates, how-to / guides, tools / generators, comparisons / alternatives, integrations / partner names, pricing, feature terms, other) with traffic sum and top 3 keywords each. One metric item per cluster, meta {cluster, keywords, traffic, examples}.
4. **SERP features**: count of top keywords whose SERP shows AI Overview, featured snippet, video, people also ask (keyword-level `serp_features` if the tool returns them). One metric item; say which field you used.
5. **Organic competitors**: `site-explorer-organic-competitors` top 10 (domain, common keywords, share). One metric item, meta list.
6. **Keyword gap vs {comparator}**: pull top 300 non-branded keywords for {comparator} too; list keywords where {domain} ranks top 10 and {comparator} is absent from the top 20 or below it (and the reverse), with volume and both positions. Items type "keyword", meta {volume, pos_domain, pos_comparator, url_domain, direction: "they_win"|"we_win"}; cap 25 each direction, sorted by volume.
7. **Top content pages**: top 20 pages by traffic with page type (template, blog, tool, landing, docs) and their top keyword. Items type "page".
Never invent values; failed calls → note + status partial. Snapshot vs history are different measures: label them.
Final message: brand share, clusters top 3, gap top 5 each way, units used.
