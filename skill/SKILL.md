---
name: marketing-osint
description: Build a marketing OSINT brief on any company from public data — positioning, business model, public economics, messages, channels, SEO, blog and content strategy, affiliates and media, what customers and AI assistants say, momentum, SWOT, what changed, per-marketing-unit briefs and (with a reader profile) a battlecard; charts and two formats (a company dossier: passport, who they sell to, how they market, how they make money, what it means for the reader as competitor / benchmark / potential client / partner; plus a detailed evidence report) with a paid-tools footer. Also compares 2-3 companies and monitors changes between runs. Use on "/marketing-osint <domain>", "OSINT on <company>", "how does <company> promote itself", "what is <competitor> emphasising", "compare <a> and <b> marketing", "what changed at <competitor>", "company dossier on <domain>", "who does <company> sell to". Output = static HTML pages (English).
---

# Marketing OSINT

Run from the repo root. Start with `README.md` (file map, commands). `SPEC.md` = decisions and lessons. `schema.json` = collector contract.
Prompt templates (use as-is, fill placeholders): `prompts/collect_ahrefs.md`, `prompts/collect_seo.md`, `prompts/collect_affiliate_media.md`, `prompts/collect_outside.md`, `prompts/ad_libraries.md`, `prompts/synthesis.md`, `prompts/factcheck.md`, `prompts/compare.md`, `prompts/dossier_enrich.md`.

## 0. Intake (ask once, bundled)
domain · brand · aliases / old names · sibling domains (renamed products, galleries) · parent company, if any (LinkedIn slug) · category phrase for AI prompts · 3-5 competitor names · comparator domain for the SEO gap (default: the reader's domain, else the main competitor) · reader profile (`reader.json` / env `OSINT_READER`, optional; see `reader.example.json`) · relationship(s) to the reader: competitor | benchmark | prospect | partner | self (drives the dossier's "What it means for me") · modes (single / compare / monitor).
State the cost before running: Ahrefs ≈ 25-30k API units per company (only if you have an Ahrefs API plan), ~20-30 LLM API calls (OpenAI / Gemini / xAI keys, each optional), 1 SimilarWeb RapidAPI call (optional), ≈ 60-90 min wall time.

## 1. Preflight (2 min)
- Ahrefs (optional): `subscription-info-limits-and-usage`, note the workspace units used (the before value for the cost reconcile); at most 2 Ahrefs agents at a time; one SEO agent at a time. No Ahrefs = the Ahrefs sources become gaps.
- `env`: OPENAI_API_KEY / GEMINI_API_KEY / XAI_API_KEY for AI visibility (no credits = `--skip xai` / `--skip gemini` and a gap), RAPIDAPI_KEY for SimilarWeb.
- Environment facts: some networks DNS-sink googletagmanager.com (stack.py uses DNS-over-HTTPS); a site that geo-redirects (/ua/, /de/) gets one /en/ visit to set its locale (common.fetch); write long Python to files, never bash heredocs; headless Chrome narrow windows render too wide.

## 2. Collect (parallel)
1. Scripts (background): `python run_collectors.py <domain> --brand "<B>" --category "<cat>" [--alt "<alias>"]` → site, wayback (quarterly), similarweb, stack, sitemap, subdomains, github, social, releases, blog (blog + /hub/ + /school/ sections), hiring, community, news, linkedin, ai_visibility. LinkedIn (opt-in: `OSINT_ENABLE_LINKEDIN=1`, only if its terms allow your use; guest page, no login; answers 999 to bursts, so the collector waits and retries once): if the company page was not found or a parent exists, rerun `python collectors/linkedin.py <domain> --brand "<B>" --slug <company-slug> [--sibling <domain2> --slug <slug2>] [--parent <parent-slug>]`. Then `python collectors/ai_visibility.py <domain> --brand "<B>" --category "<cat>" --competitor <C1> ... --retry-failed [--skip xai]`.
2. Agents (background, ≤ 5 at once, ≤ 2 of them on Ahrefs): `collect_ahrefs.md`; `collect_seo.md` (hard budget inside); `collect_affiliate_media.md`; `collect_outside.md`.
3. Main session with a browser: `ad_libraries.md` (Google, Meta, LinkedIn, Microsoft, TikTok, G2 via JSON-LD).
4. Sanity check every file (status + note) before synthesis: site language, sitemap ≥ 50 URLs, GitHub org with the domain in `blog`, ≥ 1 answering AI model, blog sections not swamped by a bulk-dated hub launch, Ahrefs current month excluded, `linkedin.json` company page website = the domain (another company can own the obvious slug).

## 3. Synthesize
One strong-model agent with `prompts/synthesis.md`, all sections in ONE pass: tldr, promise, pillars, audience, channels, say vs heard, changes, so what, key_numbers, motion, proof, content_engine, ecosystem, ai_visibility, business, datasets, company_card, swot, seo, content_strategy (blog vs hub separately), affiliate_media, department_briefs (units from the reader profile, else generic functions), battlecard and lens_block (reader profile only), sources, gaps, plus the dossier keys (7i: relationships, passport, pricing_ladder, segment levels, for_me; shapes in `prompts/dossier_enrich.md`). Pass the orchestrator's verified notes.

## 4. Gate (blocking, deterministic)
`python factcheck.py <domain> --add-evidence --fix-quotes` then `python factcheck.py <domain>` must print `0 issues`. Codes: Q non-verbatim quote, N number not in cited items, W window / basis trap, T intent-implying tone, D dashes / hype / broken encoding. Fix the analysis, never the gate. The gate checks quotes against collector text only, so step 5 is still required.

## 5. Fact-check (blocking, LLM)
Agent with `prompts/factcheck.md` (15 highest-stakes claims, fetch the live pages, collector-match for aggregates, the traps list). Apply every WRONG with a targeted edit (load, edit, dump; it may append live-verified collector items), rerun step 4 and `python build.py <domain>` (lint ok). A collector bug found here = fix the collector, re-collect, then re-apply. Never publish without both gates.

## 6. Build + visual QA
`python build.py <domain>` → `output/<domain>/index.html` (company dossier, `dossier.py`), `full.html` (detailed, all evidence), `ai_answers.html`. A missing dossier key hides its block; old analyses get the keys via `prompts/dossier_enrich.md`. Serve `output/` with `python -m http.server`. Desktop: headless Chrome `--window-size=1000,9000`. Mobile: 375x812 viewport + JS probe (`scrollWidth == innerWidth`, no element right edge > innerWidth). Table probe at 1280 and 375: no visible table wider than its container; a long note inside a nowrap `th` blanks the whole table. Check card tiles, chart labels, light + dark mode against `PRODUCT.md`.

## 7. Monitor + publish
`python monitor.py <domain>` (baseline / changes). `output/<domain>/` is a folder of static HTML: publish it on any static host, ideally behind a private link.
Compare: ONLY after every single report passed steps 4-5; any later change to a single report = regenerate the compare. `prompts/compare.md` → `python factcheck.py --compare <a> <b> --add-evidence --fix-quotes` (0) → LLM fact-check (incl. "stale vs current single reports") → apply → `python compare.py <a> <b>`. Compare company groups (all domains of a company).

## 8. Close
- Reconcile Ahrefs: workspace counter after minus before = the run's spend; fix `_run_cost.json` when concurrent agents logged overlapping deltas.
- Report: links, 3-line TL;DR, gaps, cost (footer numbers), fact-check result.
- Append SPEC.md lessons (error, root cause, fix location) when a run finds a new failure mode.

## What each marketing unit gets
Content: blog / hub cadence, topics, formats, CTAs, what ranks · SEO: brand share, clusters, keyword gap, SERP features · Paid: ad libraries, paid search, retargeting pixels · Email / lifecycle: newsletter archive, offers · Growth: offers, pricing, comparison pages · Partnerships: money SERPs, partner footprint, affiliate terms · Social: channels, creators, community · PR: media, analysts, awards, events · Design: page / ad / visual patterns.

## Cost ledger
Every paid call lands in `data/<domain>/_run_cost.json` (`costs.py`): ai_visibility and similarweb log automatically, Ahrefs agents log their units, other tools via `python costs.py <domain> <tool> <amount> <unit> "<note>"`. Footer "Paid tools used" in both formats.

## Guardrails
Public data only (no logins, sign-ups, form submits, CAPTCHA / Cloudflare bypass). Employees by role; bylines and creators counted, not named; affiliate referral IDs never printed. Reader prices only from the reader profile. A failed source is a gap, never a guess.
