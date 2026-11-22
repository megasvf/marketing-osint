# Paid orders: setup and runbook (Cloudflare Pages)

One-off paid reports with no admin panel and no database of our own. Three order modes, set by `order_mode` in
`site/business.json`:

| Mode | How a buyer orders | What you need |
|---|---|---|
| `email` (current) | The order form opens the buyer's email app with the request filled in, addressed to `order_email`; if no email app opens, the same text is shown to copy. You reply with a payment link. | `order_email` |
| `form` | The form posts to `functions/api/order.js`, which creates a Plata by mono invoice and sends the buyer to the mono payment page; the order travels in the invoice purpose and comment. | `MONO_TOKEN`, `PRICE_KOP` in Cloudflare |
| `link` | A plain payment link button (`payment_link_en` / `payment_link_uk`). | a provider with reusable payment links |

The report lives at a private link (`/r/<token>/`) for `link_ttl_days`; the link lives in the email you send.

## 1. Cloudflare Pages from the private repository (once, about 15 minutes)

1. Cloudflare dashboard → Workers & Pages → Create → Pages → **Connect to Git** → `megasvf/marketing-osint-private`.
2. Build settings:
   - Production branch: `main`
   - Framework preset: None
   - Build command: `python3 site/build_site.py notion.com figma.com miro.com linear.app`
   - Build output directory: `public`
   - Root directory: empty (repository root)
   - Environment variable: `PYTHON_VERSION` = `3.12` (the repo also has `.python-version`)
3. The build uses only the Python standard library: it rebuilds `public/` from `site/`, `output/` and `data/` (committed in
   the private repo) and keeps `public/r/` (delivered reports). `functions/` at the repository root is deployed as Pages
   Functions automatically; in `email` mode nothing calls it.
4. Custom domain: the Pages project → Custom domains → add the domain. Put `site_url` in `site/business.json`
   (for example `https://example.com`) so `deliver.py` prints full links.
5. `public/_headers` sets `noindex`, `no-referrer` and `no-store` on `/r/*`, `noindex` on the thanks pages, and long
   caching for the self-hosted fonts. Never connect the **public** repository to the production site: it has no
   `data/`, `output/` or delivered reports.

`site/business.json` is git-ignored in general but force-added in the private repository, because the Cloudflare build
reads it. Fill the seller fields before launch (`seller_name`, `seller_legal` as "ФОП <name>, РНОКПП <number>",
`seller_address`, `registration`): until then the legal pages show red "to fill" marks.

## 2. Each order (about 40 minutes, mostly waiting)

1. A request arrives at `order_email`: company website, relationship, notes, the buyer's email, language, "terms: accepted".
2. Refuse when the subject is a private individual or the purpose looks unlawful; otherwise reply with a payment link
   for the price ($15, charged in hryvnias by Plata by mono: create an invoice or payment link in the monobank business app).
3. After the payment arrives, build the report:
   ```bash
   python run_job.py <domain> --brand "<Brand>" --category "<category>" --relationship <relationship> --no-ahrefs
   ```
4. Check: `output/<domain>/index.html` opens, `data/<domain>/_logs/factcheck_report.md` was applied, and at least
   `min_sources` sources were collected. If not, tell the buyer and offer the refund the Refund policy promises.
5. Deliver (prints the private link and a ready email):
   ```bash
   python deliver.py <domain> --email <buyer> --lang <en|uk> --order <payment id>
   ```
6. Publish the report through the private repository (Cloudflare rebuilds on push):
   ```bash
   git add -f public/r data/<domain> output/<domain> && git commit -m "Deliver <domain>" && git push
   ```
7. Open the link once, then send the email from `order_email`.

## 3. Housekeeping

- Weekly: `python deliver.py --purge`, then commit and push. It deletes reports whose `link_ttl_days` have passed.
- `python deliver.py --list` shows what is live and until when.
- Corrections: rebuild the report, deliver again (new link), send the new link, delete the old folder.
- Keep payment records as tax law requires; the monobank statement is your order book.

## 4. Switching to the automatic mono form later

1. Turn on internet acquiring (Plata by mono) in the monobank business cabinet and create its API token.
2. Pages project → Settings → Environment variables (Production): `MONO_TOKEN` (Secret) and `PRICE_KOP` (price in kopiyky);
   optional `BASKET=1` if automatic fiscal receipts are on.
3. Set `order_mode` to `form`, push. Test with `PRICE_KOP=100` (1 hryvnia) and refund it in the app. The `comment` and
   `customerEmails` fields in `merchantPaymInfo` are not confirmed by a live test yet; if mono rejects them (see the Pages
   logs), remove them from `functions/api/order.js`.

## 5. Legal pages: what they cover and what to check

The terms, privacy notice, refund policy and contact page are plain-language drafts written without a lawyer. They cover:
who sells; the service (marketing research for businesses) and delivery; payment and receipts; refusals; the private link
and its lifetime; accuracy limits; permitted use; the EU/UK 14-day withdrawal right and how it ends on delivery (the form
asks for that consent); liability capped at the price; complaints; the data you collect, why, where it is kept, who
processes it, transfers abroad, retention, rights, and no cookies. Check with an accountant before the first real payment:
- FOP group and tax rate for selling information services to foreign buyers.
- Fiscal receipts (PRRO) for card payments.
- EU VAT: business buyers are reverse-charged; sales to EU consumers can make a non-EU seller liable for EU VAT.
- That `seller_legal`, `seller_address` and `registration` match the FOP record exactly.
