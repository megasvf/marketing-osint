# Paid orders: setup and runbook (Plata by mono + Cloudflare Pages)

One-off paid reports with no admin panel and no database of our own. The order lives in the monobank invoice, the report
lives at a private link for `link_ttl_days`, the link lives in the email you send.

```
buyer → order.html form (domain, relationship, notes, email, consent)
      → /api/order (Cloudflare Pages Function, site/cloudflare/functions/api/order.js)
      → monobank invoice/create → pay.mbnk.biz payment page → thanks.html
monobank app → you see the payment; its destination and comment hold the domain, relationship, email and notes
you → run_job.py → deliver.py → deploy → send the email with the private link
```

Seller: a FOP with a monobank business account and Plata by mono (internet acquiring). Fees per monobank's page:
1.3% per card payment, 2% for foreign cards ([monobank e-comm](https://monobank.ua/e-comm)). Prices are in hryvnias;
foreign buyers pay by card and their bank converts. Not legal or tax advice: check the points in section 4 with an accountant.

## 1. One-time setup (about 1 hour)

1. **Plata by mono.** In the monobank business app or web cabinet, turn on internet acquiring (Plata by mono) for the FOP
   account and create an API token for it. That token is the `X-Token` the function sends.
2. **Business details.** Copy `site/business.example.json` to `site/business.json` (git-ignored) and fill every field:
   `seller_name`, `seller_legal` ("ФОП <name>, РНОКПП <number>"), `seller_address`, `seller_country`, `registration`,
   `contact_email`, `price` (as shown, for example "1 990 грн"), `tax_note`, `email_provider`, `governing_law` (Ukraine).
   Keys ending in `_uk` override the value on Ukrainian pages. `order_mode` stays `form`.
3. **Email.** Use an address on your own domain for `contact_email` (Cloudflare Email Routing forwards it to your mailbox
   for free) and name the mailbox provider in `email_provider`.
4. **Cloudflare Pages project.** Create a project (Direct Upload) and add your domain. In Settings → Environment variables
   (Production) add:
   - `MONO_TOKEN`: the Plata by mono token, type **Secret**
   - `PRICE_KOP`: the price in kopiyky, for example `199000` for 1 990 UAH (must match `price` on the site)
   - optional `BASKET=1` if automatic fiscal receipts are on (sends a one-line basket with the invoice)
5. **Build and deploy** (the function is picked up from `site/cloudflare/functions/`):
   ```bash
   python site/build_site.py notion.com figma.com miro.com linear.app
   ```
   ```bash
   cd site/cloudflare && npx wrangler pages deploy ../../public --project-name marketing-osint
   ```
   `public/_headers` sets `noindex`, `no-referrer` and `no-store` on `/r/*`, `noindex` on the thanks pages, and long caching
   for the self-hosted fonts. Never deploy `public/` from a public Git repository: delivered reports would be readable there.
6. **Test with 1 hryvnia.** Set `PRICE_KOP=100`, deploy, order a report for any domain, pay with your own card, and check
   the payment in the monobank app: the purpose should read "Marketing OSINT report: <domain>" and the comment should hold
   the relationship, email and notes. Refund it in the app, set `PRICE_KOP` back, deploy again.
   The fields `comment` and `customerEmails` inside `merchantPaymInfo` are not confirmed by a live test yet; if the test shows
   an error in the Pages logs ("mono invoice/create failed"), remove them from `order.js` and keep `reference` + `destination`.

## 2. Each order (about 40 minutes, mostly waiting)

1. The monobank app notifies you of the payment. Open it: the purpose holds the domain; the comment holds
   `domain | relationship | email | lang | notes`.
2. Refuse when the subject is a private individual or the purpose looks unlawful: refund in full in the app and reply to the buyer.
3. Build the report:
   ```bash
   python run_job.py <domain> --brand "<Brand>" --category "<category>" --relationship <relationship> --no-ahrefs
   ```
   Add `--alt` / `--competitor` from the notes.
4. Check: `output/<domain>/index.html` opens, `data/<domain>/_logs/factcheck_report.md` was applied, and at least
   `min_sources` sources were collected. If not, tell the buyer and offer the refund the Refund policy promises.
5. Deliver (lang from the comment):
   ```bash
   python deliver.py <domain> --email <buyer> --lang <en|uk> --order <invoice reference>
   ```
6. Deploy again (step 1.5), open the link once, then send the email from `contact_email`.

## 3. Housekeeping

- Weekly: `python deliver.py --purge`, then deploy. It deletes reports whose `link_ttl_days` have passed.
- `python deliver.py --list` shows what is live and until when.
- Corrections: rebuild the report, deliver again (new link), send the new link, delete the old folder.
- Keep the provider's payment records as tax law requires; they are your order book.

## 4. Legal pages: what they cover and what to check

The terms, privacy notice, refund policy and contact page are plain-language drafts written without a lawyer. They cover:
who sells; the service and delivery; payment and receipts; refusals; the private link and its lifetime; accuracy limits;
permitted use; the EU/UK 14-day withdrawal right and how it ends on delivery (the form asks for that consent); liability
capped at the price; complaints; the data you collect, why, where it is kept, who processes it, transfers abroad,
retention, rights, and no cookies. Check with an accountant before the first real payment:
- FOP group and tax rate for selling information services to foreign buyers.
- Fiscal receipts (PRRO): card payments to a FOP usually need them; Plata by mono offers automatic fiscalization (then set `BASKET=1`).
- EU VAT: business buyers are reverse-charged, but sales to EU consumers can make a non-EU seller liable for EU VAT from the
  first sale. The simplest position is to sell for business use only; the Terms describe the service as marketing research
  for organisations.
- That `seller_legal`, `seller_address` and `registration` match the FOP record exactly.
