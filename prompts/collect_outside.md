# Collector prompt — outside-in layer (sonnet, background)

Placeholders: {domain}, {brand}, {aliases} (old names, product names, sibling brands).
Your final message IS the deliverable; finish, do not defer. Public data only: no logins, no sign-ups, no form submissions, employees by role (C-level names only for public announcements). ToolSearch "select:WebFetch,WebSearch"; WebFetch every page you cite; never cite search snippets.

Follow the item contract in `schema.json`; if an earlier run exists in `data/`, copy its `earned.json`, `marketplaces.json`, `email_archive.json`, `corporate.json` item shapes.

Write four files under `data/{domain}/` (contract in `schema.json`; text ≤ 40 words, quote verbatim ≤ 25 words, url REQUIRED and fetched, no em dashes):
1. `earned.json`: official review score + count per platform with meta `platform`, `rating` (number), `review_count` (number). Trustpilot, Product Hunt, marketplace listings (AWS, HubSpot...). G2 and Capterra usually 403 for WebFetch: leave them to the orchestrator's browser pass and say so. Praise / complaint themes with short verbatim quotes, flag affiliate / competitor-authored / AI-summary sources in meta. Press and PR last 12 months, events, podcasts. Count past events only (date ≤ fetch date); list upcoming ones separately with meta `upcoming: true`.
2. `marketplaces.json`: app/integration listings (HubSpot, Salesforce AppExchange, Zapier, Shopify, Chrome Web Store, Figma, Google Workspace, AWS Marketplace, category partner directories): meta `marketplace`, `rating`, `review_count`, `installs`; affiliate / partner / agency / startup programs with their terms.
3. `email_archive.json`: the company's emails in public email archives. Subject, theme, offer type.
4. `corporate.json`: last 18 months: leadership changes, funding / M&A, parent-company investor statements (quote the period and currency basis of every growth figure: reported vs constant FX, EUR vs USD), pricing reviews, security / compliance pages, customer-count claims, awards.

Never invent ratings, counts, dates or quotes; output granularity = source granularity. Record self-reported figures exactly as each page shows them, with the page URL, so differences between pages are visible.
Final message: per file status, item count, 3 telling findings, what was blocked.
