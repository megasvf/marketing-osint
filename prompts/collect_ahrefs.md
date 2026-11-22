# Collector prompt — Ahrefs (haiku, background)

Placeholders: {domain}, {siblings} (other domains of the same company, e.g. a renamed product's domain; may be empty).
Your final message IS the deliverable; finish, do not defer.

Use the Ahrefs MCP (ToolSearch; tool names contain `Ahrefs` or the Ahrefs server name). Call `doc` before first use of each tool. Money values are USD cents. Ignore render_with hints; never call render tools. Call `subscription-info-limits-and-usage` at start and end and report units used. Then record them: `python costs.py {domain} "Ahrefs API" <units> units "<what was pulled>"` (run in the repo root; shown in the report footer). Rows ≤ 50. Mode = subdomains.

Follow the item contract in `schema.json` exactly; if an earlier run of any company exists in `data/`, copy its `ahrefs_paid.json`, `ahrefs_organic.json`, `ahrefs_history.json` item shapes.

Write under `data/{domain}/` (contract in `schema.json`, `"domain": "{domain}"`):
1. `ahrefs_paid.json`: paid pages, paid keywords count, paid traffic for {domain} (+ {siblings}).
2. `ahrefs_organic.json`: metrics (snapshot), top 30 pages by traffic, top 50 NON-branded keywords for {domain} (+ metrics for {siblings}).
3. `ahrefs_history.json`: 24 monthly points for organic_traffic, paid_traffic, organic_keywords (sum of position buckets), domain_rating, refdomains for {domain} and each sibling, meta `{"domain","metric","points":[{"date":"YYYY-MM-01","value":N}]}`; newest 20 referring domains (last 90 days, with DR and first_seen); top 15 anchors.
4. `ai_perception.json`: Brand Radar only if a report for this brand exists (`management-brand-radar-reports`); else status unavailable with "no Brand Radar report for <brand>". Do not create reports.

Rules: the current month is partial; keep it in the series but flag it in the note. Snapshot metrics and monthly history are different measures: say which is which in item text. Aggregate url: `https://app.ahrefs.com/site-explorer/overview/v2/subdomains/live?target={domain}`. Never invent values; a failed call → status partial + note. No em dashes.
Final message: per file status, item counts, 3 telling numbers, units used.
