# Marketing OSINT

A Claude Code skill and a set of scripts that build a marketing brief on any company from public data. The brief covers positioning, business model, public economics, messages, channels, SEO, blog and content strategy, affiliates and media, reviews, what AI assistants say, momentum, SWOT, what changed since the last run and briefs per marketing unit. With an optional reader profile (your own company) it also adds a battlecard and a price check.

Each company gets two formats. The company dossier (`index.html`) covers passport, bottom line with top moves, who they sell to, how they market, what they say, how they make money (price ladder), momentum, what others say, strengths and weaknesses, and "What it means for me". The detailed report with charts and every evidence link is `full.html`. "What it means for me" follows the company's relationship to the reader, set at intake: competitor (battlecard), benchmark (what to borrow, per marketing unit), potential client (ideal-customer fit, buyers by role, visible pains, way in), partner (shared audience, joint ideas, risks) or the reader's own company. The tool can also compare 2 or 3 companies and track changes between runs. Reports are in English and are static HTML you can host anywhere.

## Repository layout

| Path | What |
|---|---|
| `skill/SKILL.md` | The skill: step-by-step runbook. Install it as `.claude/skills/marketing-osint/SKILL.md` |
| `SPEC.md` | Decisions by version, lessons table (error, root cause, fix), open items |
| `schema.json` | Collector contract: `{source, domain, fetched_at, status, note, items[{type, text, quote, url, date, meta}]}` |
| `PRODUCT.md`, `DESIGN.md`, `design/` | Design brief, design system, tokens and brand constants |
| `collectors/*.py` | Script collectors; `common.py` = fetch with geo-locale guard + page signals |
| `run_collectors.py` | Runs every script collector for one domain |
| `prompts/collect_*.md`, `prompts/ad_libraries.md` | Agent collectors (Ahrefs, SEO, affiliates and media, outside-in layer, browser pass) |
| `prompts/synthesis.md`, `factcheck.md`, `compare.md` | Synthesis rules, LLM fact-check, comparison |
| `factcheck.py` | Deterministic gate: Q non-verbatim quote, N unsupported number, W window or basis trap, T intent-implying tone, D dashes / hype / broken encoding |
| `build.py`, `charts.py`, `report_charts.py` | `analysis.json` → HTML pages and charts built from collector numbers |
| `dossier.py` | The company dossier page (`index.html`) |
| `prompts/dossier_enrich.md` | Adds the dossier keys (passport, price ladder, segment levels, relationships, "What it means for me") to an existing analysis |
| `compare.py`, `monitor.py` | Comparison page; snapshots and diffs between runs |
| `costs.py` | Paid-tools ledger → "Paid tools used in this run" footer |
| `site/build_site.py`, `site/content_en.py`, `site/content_uk.py` | Site in English (`public/`) and Ukrainian (`public/uk/`): home, order page, thanks page, terms, privacy, refunds, contact; copies of example reports |
| `site/business.example.json` | Seller details, price, order mode and payment links (copy to the git-ignored `site/business.json`) |
| `run_job.py` | Headless runner: one command from collectors to a built, fact-checked report |
| `deliver.py` | Puts a paid report at a private link (`public/r/<token>/`), prints the email; `--purge` removes expired links |
| `docs/ORDERS.md` | Paid orders: Plata by mono order form (Cloudflare Pages Function `site/cloudflare/functions/api/order.js`), setup and the per-order runbook |

`data/` (collector output), `output/` (built pages) and `reader.json` (your reader profile) are git-ignored and never committed. `reader.py` loads the profile.

## Pipeline

1. **Collect.** Script collectors and agent collectors run in parallel and write `data/<domain>/<source>.json`.
2. **Synthesize.** An agent turns the files into `analysis.json`.
3. **Gate.** `factcheck.py` must report 0 issues.
4. **Fact-check.** An LLM agent opens the live pages behind the highest-stakes claims.
5. **Build, monitor, publish.** `build.py`, then `monitor.py`, then publish.

A source that fails is shown as a gap, never guessed.

```bash
python run_collectors.py example.com --brand Example --category "form builder" --alt "Old Name"
python collectors/ai_visibility.py example.com --brand Example --category "form builder" --competitor Rival --retry-failed
python factcheck.py example.com --add-evidence --fix-quotes
python factcheck.py example.com
python build.py example.com
python monitor.py example.com
python compare.py example.com rival.com
python costs.py example.com --show
```

## Sources

### Free sources (public data, no paid account)

| Source | What it gives | Collector |
|---|---|---|
| Company website: home, pricing, features, about, integrations | H1/H2, CTAs, offers, prices, claims | `site.py` |
| Pricing page, both billing modes (Playwright toggle clicks) | Monthly and yearly plan prices, default toggle | `pricing.py` + `pricing_capture.js` |
| Wayback Machine (CDX API) | Home and pricing 3, 6, 9 and 12 months ago | `wayback.py` |
| Sitemaps | Page inventory by type: templates, blog, comparison pages | `sitemap.py` |
| Blog and hub pages | Cadence, topics, funnel stage, word count, CTAs, bylines (counted, not named) | `blog.py` |
| Changelog / release notes (incl. Beamer) | Release cadence, product focus | `releases.py` |
| Page HTML + Google Tag Manager container (via Cloudflare DNS-over-HTTPS) | Ad pixels and martech stack | `stack.py` |
| crt.sh (certificate transparency; Cert Spotter fallback) | Subdomains: new products, tools, campaigns | `subdomains.py` |
| GitHub API (unauthenticated) | Public repos, SDKs, developer activity | `github.py` |
| LinkedIn public company page (guest view, no login) | People who list the company as employer (team-size proxy), size band, HQ, founded year, followers; the parent company's page when a group owns it | `linkedin.py` |
| Social profiles, YouTube `/videos` page | Channels, cadence, video themes | `social.py` |
| Greenhouse, Lever, Ashby, Workable boards, LinkedIn guest jobs | Open roles as channel bets | `hiring.py` |
| Reddit, Hacker News (Algolia API), Product Hunt | Community mentions and sentiment | `community.py` |
| Google News RSS | Press coverage | `news.py` |
| Google Ads Transparency Center, Meta Ad Library, LinkedIn Ad Library, Microsoft Ad Library, TikTok Ad Library | Ad counts, creatives, themes (read in the browser) | `prompts/ad_libraries.md` |
| G2 (JSON-LD rating), Trustpilot, Product Hunt, Capterra if reachable | Official rating and review count, praise and complaint themes | `prompts/ad_libraries.md`, `prompts/collect_outside.md` |
| App marketplaces: HubSpot, Salesforce AppExchange, Zapier, Shopify, Chrome Web Store, Figma, Google Workspace, AWS Marketplace, category partner directories | Listings, ratings, installs | `prompts/collect_outside.md` |
| Public email archives: Really Good Emails, Milled, own newsletter archive | Email subjects, themes, offers | `prompts/collect_outside.md` |
| Company news, press releases, investor statements | Leadership, funding, M&A, pricing reviews | `prompts/collect_outside.md` |
| Web search (the agent's built-in search) + affiliate program pages | Creator videos, affiliate terms, best-of lists | `prompts/collect_affiliate_media.md` |

### Paid sources

| Source | Billing | What it gives | Typical use per company |
|---|---|---|---|
| Ahrefs API (via the Ahrefs MCP) | Plan quota (API units) | Organic and paid keywords, top pages, 24-month history, backlinks and referring domains, SERP overview for money searches, keyword gap, Brand Radar (only if a report already exists) | ≈ 25-30k units; SEO agent capped at 15k |
| SimilarWeb via RapidAPI | Pay per use | Visits, channel mix, countries | 1 call or 0 (reuses a monthly snapshot ≤ 45 days old) |
| OpenAI API (gpt-5.5 with web search) | Pay per use | AI visibility: answers to 10 category prompts | ~10 calls |
| Google Gemini API (search grounding) | Pay per use | AI visibility, second model | ~10 calls |
| xAI API (Grok) | Pay per use | AI visibility, third model | ~10 calls |

Experimental: `collectors/dataforseo.py` pulls the SEO, backlink and multi-model AI-answer data from one pay-as-you-go DataForSEO account (env `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD`) into `dfs_*.json` for a side-by-side test against Ahrefs. Its numbers come from different models than Ahrefs: never mix the two in one series. `--dry-run` prints the planned calls and price.

Every paid call is logged to `data/<domain>/_run_cost.json` and shown in the report footer. Keys come from environment variables only (`OPENAI_API_KEY`, `GEMINI_API_KEY`, `XAI_API_KEY`, `RAPIDAPI_KEY`); a missing key skips that provider and the gap is shown in the report.

### Reader profile (optional)

Copy `reader.example.json` to `reader.json` (git-ignored) or point env `OSINT_READER` at a JSON file. It holds your company's name, domain, public prices, ideal-customer criteria, marketing units and house rules. With it, reports add a battlecard, a price check and "What it means for <your company>". Without it, reports stay neutral.

## Requirements

- Python 3.11+ with `requests` and `beautifulsoup4`; Claude Code with agents, web fetch and a browser tool for the ad libraries.
- MCP servers: Ahrefs (optional, paid API plan).
- Every paid source is optional: a missing key or account becomes a gap in the report, never a guess.

## Guardrails

- Public data only: no logins, sign-ups or form submits, and no CAPTCHA or Cloudflare bypass.
- Employees are named by role. Bylines and creators are counted, not named. Affiliate referral IDs are never printed.
- A failed source is a gap, never a guess.

## Terms of the sites you read

The collectors read public pages only and never log in, sign up or bypass bot protection. Some sites forbid automated access in
their terms even for public pages. LinkedIn (company page and guest job search) and G2 are therefore off by default; turn them on
only if you are allowed to: `OSINT_ENABLE_LINKEDIN=1`, `OSINT_ENABLE_G2=1`.

## Not affiliated

Example reports name real companies (Notion, Figma, Miro, Linear and others) from public information. This project is not
affiliated with, endorsed by or sponsored by them; their names and marks belong to their owners.

## License

Copyright (C) 2026 megasvf and contributors.


[GNU Affero General Public License v3.0](LICENSE). You may use, change and share the code. If you run a changed version as a network service, you must offer its users the source of your changes.
