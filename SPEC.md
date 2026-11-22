# Marketing OSINT — decisions and lessons

Input: one company domain. Output: static HTML pages: a company dossier (`index.html`), a detailed evidence report (`full.html`) and the raw AI answers (`ai_answers.html`). They show how the company promotes itself (what it stresses, to whom, where) and what that means for the reader.

## Decisions
- Universal: any company, no product binding. Neutral by default; an optional reader profile (`reader.json`, see `reader.py`) adds a battlecard, a price check and "What it means for <reader>".
- Public data only: no fake accounts, no logins, no sign-ups, no data on private individuals. Newsletter sign-up is never automatic.
- Every fact links to its source. A source that fails is shown as a gap, never guessed.
- Two blocking gates before any page ships: the deterministic `factcheck.py` (0 issues) and an LLM fact-check against live pages (`prompts/factcheck.md`).
- Charts are built from collector numbers, not from the synthesis text.
- Paid tools are optional and logged per run (`costs.py`), shown in the report footer.
- Report language: English.

## Versions
- v1: one company, owned pages + Wayback + Ahrefs + SimilarWeb + ad libraries + reviews + hiring; one HTML page with numbered citations.
- v2: 21 sources (+ ahrefs_history, ai_visibility, stack, sitemap, subdomains, community, news, github, marketplaces, email_archive, corporate); short and detailed formats; compare mode; monitor (snapshots and diffs).
- v3: company card, momentum, moves in 90 days, SWOT, battlecard; `releases` collector; deterministic gate `factcheck.py`; agent prompts as files.
- v4: `blog.py`, SEO deep dive, affiliates and media, per-unit briefs, cost footer.
- v5: company dossier replaces the short format; relationships (competitor, benchmark, prospect, partner, self); `linkedin.py`.
- v6: open-source cleanup (+ design system, generic collectors, showcase site, examples: Notion, Figma, Miro): reader profile replaces the single-company lens; private sources removed; SimilarWeb collector self-contained (`RAPIDAPI_KEY`).
- v7: headless runner (run_job.py), pricing in both billing modes, board department labels, citations by site; paid one-off orders (order form → Cloudflare Pages Function → Plata by mono invoice, or a plain payment link) with private-link delivery (deliver.py), legal pages, Ukrainian site, self-hosted fonts.

## Lessons log (each fixed in code or prompts)
| Error found | Root cause | Fix (where) |
|---|---|---|
| "4x organic growth" | Ahrefs partial current month used | prompts traps + gate W + charts drop the current month |
| AI "rank 10 of 14", co-mentions undercounted | list parser | ai_visibility.py mention-order logic + candidate filter |
| Homepage sections "removed" | collector keeps H1/H2 only | prompts trap "missing heading is not removal" |
| Affiliate "before" state | later company statement taken as history | prompts trap "a before state needs a dated source" |
| ARR growth series mixed EUR and USD | basis not recorded | collect_outside.md asks for period + basis |
| Pages collected in the wrong language | IP geo redirect | common.fetch /en/ locale guard |
| Sitemap with 17 URLs | urlset used as index | sitemap.py malformed-index detection |
| Wrong GitHub account | name-only match | github.py prefers blog = domain |
| GTM pixels missing | local DNS sink | stack.py DoH + curl --resolve |
| G2 "blocked" | plain fetch gets 403 | ad_libraries.md: G2 via a browser |
| Paraphrases shown as quotes | agents write quotes | gate Q + `--fix-quotes` |
| Numbers without evidence | evidence not attached | gate N + `--add-evidence` |
| API key in an error string | key in URL query | key in header + error scrubbing |
| G2 "2 reviews" (real 0) | page-text regex | ad_libraries.md: JSON-LD aggregateRating only; none = 0 |
| Quotes that pass the gate but are not on the page | collectors stored paraphrases in `quote` | factcheck.md: verbatim vs live page; collect_*.md: quote = page text only |
| `�` in quotes | broken decoding in collectors | gate D flags U+FFFD |
| AI answer "brand ranked first" (real third) | mention order differs from the answer's own ranked table | per-prompt positions hand-read from `_ai_raw.json` |
| Compare stale after single-report fixes | compare written before final single reports | compare only after both single reports pass both gates |
| Organic "-51%" in a compare | single domain vs company group | compare company groups (all domains) |
| SEO collector burned ~96k Ahrefs units (estimate 5-8k) | 250-row pages + per-keyword lookups, 4 Ahrefs agents in parallel | collect_seo.md hard budget (≤ 12 calls, ≤ 100 rows, stop at 15k); ≤ 2 Ahrefs agents at once |
| Concurrent agents logged overlapping unit deltas | each agent read the shared counter | reconcile with the workspace counter delta after a round |
| Affiliate referral IDs collected | referral links carry personal handles | never print affiliate IDs, count them only |
| Blog share of top-page traffic 5.4% (real 4.4%) | www and non-www URLs merged by overwrite | blog.py sums duplicate keys |
| "New Wikipedia coverage" (article deleted) | Ahrefs first-seen link, page not opened | factcheck.md: open every media link; a 404 is not coverage |
| Partner post counted as third-party listing | post on the company's behalf misread as external | collect_affiliate_media.md: check who authored partner posts |
| AI Overview counted as an owned SERP slot | SERP feature counted as a page | AI Overview = separate type, say "results" |
| Hub articles missing from blog metrics | path segments lacked hub / school | BLOG_SEG += hub, school |
| "Comparison terms bring 0.1%" | branded vs / alternatives queries excluded from the non-branded split | say which split a share comes from |
| Compare "neither brand answers its decision searches" | one query per brand generalised | compare.md: name the query; "neither / both" needs every query checked |
| "New in 2026" media links | Ahrefs first-seen read as publish date | "first seen by Ahrefs" wording |
| Webinar count off by one | an upcoming session counted | collect_outside.md: past events only (date ≤ fetch date) |
| Compare head-to-head showed only row names | note inside a nowrap `th`, table grew to 2,110 px | compare.py `th.h2h-d` wraps; table probe in QA |
| Channel matrix "no data" for an active channel | first regex bucket won | compare.py: every matching bucket |
| Effort pills looked like verdicts | effort scale mapped to verdict colours | neutral ramp v-heavy / v-active / v-light |
| Uneven x-axis months, wrapping dates | evenly spaced indices; narrow date column | charts._xticks calendar-aligned; nowrap date column |
| HQ and founding year "not public" although on the site | enrich agent read collectors only | dossier_enrich.md: about page + footer first |
| Customer count from an AI summary; ARR rounded up | secondary source + rounded headline | dossier_enrich.md: primary sources, exact figures |
| Seats taken from a third-party review | pricing matrix not fetched | dossier_enrich.md: seats from the live matrix; units differ across vendors |
| Verdict claimed more than its points showed | verdict written beyond the points | dossier_enrich.md: verdict restates points only |
| Heredoc wrote `\b` as a backspace (filter silently dead) | bash heredoc + Python escapes | write scripts to files; check after shell edits |
| Team size "not public" | no LinkedIn or parent-company source | collectors/linkedin.py + parent page; dossier_enrich.md team size + HQ rules |
| LinkedIn page of a different company with the same name | slug guessed from the brand | linkedin.py accepts a page only when its Website field is the domain |
| Build crashed on ad counts like "~2K" | libraries show rounded labels, collectors store them as text | report_charts.ad_count parses them (charts, compare, monitor) |
| Yearly-billed prices shown under "Monthly"; annual-only plans shown as "Quote" | ladder read `price` only | dossier.money falls back to `price_yearly` and labels it "(yearly)"; columns "Billed monthly" / "Billed yearly" |
| Stale deal status ("announced" after it closed) passed the gate | the gate checks numbers and quotes, not freshness | LLM fact-check opens the newest primary source for any deal, funding or leadership claim |
| "Most cited domain" true only across brand-named prompts | citation counts mixed prompt sets | say whether a count covers all prompts or the brandless ones |
| An open-sales-roles count that a recount did not reproduce | agents counted job titles by hand; the gate skipped numbers under 100 | hiring.py role_families / role_cities metrics; gate checks 10-99 counts |
| AI "mention order 1 of 11" read as a rank | the collector's parsed list length, not the answer's own list | ai_visibility.py rank = position in the answer's own ranked list or table; citations split all vs brandless |
| Yearly prices read as monthly | pricing pages load on yearly billing; the site collector saw one mode | collectors/pricing.py switches the toggle (Playwright) and records both modes; prices the toggle does not change are labelled |
| Subdomains always a gap | crt.sh answers 502 | subdomains.py falls back to Cert Spotter |
| Marketing and sales role counts swapped against the job board's own labels | title rules guessed the function | hiring.py reads the job board's own team / department labels (role_departments) and prefers them |
| A site undercounted because its help-centre subdomain was counted separately | citations counted per hostname | ai_visibility.py groups citations by site (subdomains grouped); in one example the brandless-prompt leader changed once subdomains were grouped |
| Agent's own sum "12 of 32" passed into a draft | arithmetic on collector counts | the 10-99 count gate catches it; synthesis rule: no sums that are not collector items |

## Open items
1. blog.py: per-section metrics (blog / hub / resources / school) and a per-section "40 newest" sample; a bulk-dated hub launch can swamp the blog cadence.
2. releases.py: undercounts long totals on paginated changelogs ("Load More"); 90-day windows are correct, so metric text says "at least N".
3. Wayback: archive.org was unreachable from the cloud sandbox used for the examples; no fallback history source yet (Common Crawl index was unreachable there too).
4. Capterra / G2 / Product Hunt / LinkedIn ad library are bot-protected; they stay gaps.
5. run_job.py: first full run done (linear.app, 35 min, $5.59 of agent cost, gate 0, 14 fact-check rewrites applied). Ahrefs is not visible to headless agents unless an Ahrefs MCP server with an API key is passed via --mcp-config.
6. collectors/dataforseo.py is written and dry-run tested; no account yet, so no side-by-side with Ahrefs.
