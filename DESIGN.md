# Design system

One system for the report pages (dossier, detailed report, comparison, raw AI answers) and the showcase site.
Sources of truth: `design/tokens.css` (every color, font and radius) and `design/brand.py` (name, fonts link, logo, favicon).
Pages never hard-code a color: they use the tokens below.

## Idea
The product reads a company from the outside and marks what matters, like a highlighter on a printed dossier.
So the look is editorial and evidence-first: serif headlines, plain sans body, small mono citation numbers,
lots of white, and one teal highlighter used sparingly.

## Name and mark
- Name: **Marketing OSINT**. Rename in `design/brand.py` only.
- Tagline: "See how any company markets itself, from public data".
- Mark: a dark rounded tile with a teal lens set off-centre and a short bar under it: an outside view of a page.
  It inverts in dark mode (the tile takes `--ink`). Minimum size 16 px. No other logo colors.

## Color
| Token | Light | Dark | Use |
|---|---|---|---|
| `--ink` | #16181d | #eceef2 | text, primary marks, the logo tile |
| `--ink-2` | #4d5260 | #aeb3be | secondary text, captions, axes |
| `--line` | #e2e4e9 | #2c2f36 | rules, table borders |
| `--bg` | #ffffff | #111317 | page |
| `--surf` | #f4f5f7 | #1a1d22 | callouts, verdict boxes, nav hover |
| `--brand` | #0b6b66 | #5ccfc2 | logo lens and any accent text (6.4:1 on white, 9.9:1 on the dark page). Never a chart series or a verdict color |
| `--mark` | #b9e8e1 | #0f514c | the highlighter band under 1-3 words (`.hl`), at most once per screen; text on it keeps `--ink` (13:1 light, 7.9:1 dark) |
| `--s1` `--s2` `--s3` | #2a78d6 #eb6834 #8a5cf0 | #3987e5 #d95926 #9a78f5 | chart series (blue, orange, violet), fixed order, never cycled |
| `--ok` `--warn` `--bad` `--none` (+ `-bg`) | | | verdicts only (confirmed / mixed / contradicted / no data), always with a text label |

Chart series were run through the dataviz palette validator: light and dark pass lightness, chroma, CVD (worst adjacent ΔE 24.7), normal-vision and 3:1 contrast checks.
The third series is violet, not green, so charts never read as the teal accent or the green "confirmed" verdict.
Effort levels (heavy / active / light) use a neutral ink ramp, not verdict colors.

## Type
| Role | Family | Size / weight |
|---|---|---|
| Page title (h1) | Source Serif 4 | 32 / 700 |
| Section title (h2) | Source Serif 4 | 21 / 700 |
| Body, tables, UI | Inter | 15 / 400, 600 for emphasis; 13-14 in tables |
| Citations, code, raw numbers in source lists | JetBrains Mono | 10-13 / 500-600 |
Tabular numbers (`font-variant-numeric: tabular-nums`) wherever numbers line up.

## Shape and spacing
Radii `--r-s` 6, `--r-m` 10, `--r-l` 16. Sections are separated by a 1 px `--line` rule and 24 px padding, not by cards.
Content width 1040 px (reports), 1120 px (site). Phone: 16 px side gutter, no horizontal scroll, tables scroll inside their own wrapper.

## Components
- **Citation** `.cite`: a mono superscript number linking to the source; the same URL keeps the same number on the page.
- **Pill** `.pill.v-*`: verdict with a word, never color alone.
- **Relationship chip** `.rel-*`: competitor / benchmark / prospect / partner / own company.
- **Verdict box** `.dz-verdict`: `--surf` background, one sentence, one link.
- **Coverage strip**: one dot per source: filled = collected, half = partial, dashed = unavailable.
- **Highlighter** `.hl`: a teal band (`--mark`) under 1-3 words, text stays `--ink`; at most once per screen.

## Rules
- Answer first; every claim one click from its source; gaps shown, never hidden.
- No gradients (except the `.hl` band), no shadows for decoration, no card grids, no hero dashboards.
- Dark mode is its own token set, chosen by `prefers-color-scheme` or `data-theme="dark"` on `<html>`.
