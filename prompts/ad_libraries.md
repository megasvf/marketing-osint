# Ad libraries + G2 — main session, built-in Browser pane

Subagents may lack the browser; do this in the main session. Read-only: no sign-in, no CAPTCHA or Cloudflare challenge (if "Just a moment..." or a CAPTCHA appears, stop and record the platform as blocked).

1. **Google Ads Transparency**: `https://adstransparency.google.com/?region=anywhere&domain=<domain>&hl=en` → count + advertiser ids (links `advertiser/AR...`). Advertiser page: legal name, total ads ("~500"), then `&preset-date=Last%2030%20days` for the 30-day count. Repeat for sibling domains.
2. **Meta Ad Library**: type the brand into the search box (set value via JS + input event), read the typeahead "Advertisers" list, click the right page → `view_all_page_id`. Open `active_status=all` (all-time count, recent date ranges, sample text) and `active_status=active` (active count). Keyword search is too noisy; do not use it for counts.
3. **LinkedIn Ad Library**: `https://www.linkedin.com/ad-library/search?accountOwner=<brand>` → "N ads match", cards via `a[href*="/ad-library/detail/"]` (first page ≈ 24). Record theme per creative and promoter by ROLE (brand page vs employee / ambassador thought-leader ad), never names.
4. **Microsoft Ad Library**: `adlibrary.ads.microsoft.com`, search box via form_input + Return (the page may write to the OS clipboard: warn the user).
5. **TikTok Ad Library**: `library.tiktok.com/ads?region=all`, set the search input value + click Search; EU/UK scope, last 30 days.
6. **G2** (only when the operator set OSINT_ENABLE_G2=1; G2's terms restrict automated access): `https://www.g2.com/search?query=<brand>` → product slugs (also old product names); on each product page read `script[type="application/ld+json"]` aggregateRating (ratingValue, reviewCount); no aggregateRating in the JSON-LD = 0 reviews (never regex the page text for 'N reviews', it matches other widgets) and 2-3 "What do you like / dislike" snippets (≤ 25 words). Capterra is Cloudflare-gated: record as blocked.

Write `data/<domain>/ad_libraries.json` via `data/<domain>/_ad_libraries_build.py` (metric items with meta {platform, total_ads, last_30_days?, active?}, ad items with meta {platform, theme, promoter}). Append G2 items to `earned.json` with meta {platform: "G2", rating, review_count}.
