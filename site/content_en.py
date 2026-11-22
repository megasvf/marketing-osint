"""English copy for the site. Strings may hold simple trusted HTML.
{placeholders} are filled from site/business.json; a missing value renders as a visible "to fill" mark.
Keep content_uk.py in the same shape: same keys, same placeholders."""

LANG = "en"
HTML_LANG = "en"
LABEL = "English"

UI = {
    "nav_examples": "Examples", "nav_how": "How it works", "nav_sources": "Sources", "nav_run": "Run it",
    "nav_order": "Order a report", "nav_github": "GitHub", "lang_switch": "Українською",
    "foot_terms": "Terms", "foot_privacy": "Privacy", "foot_refunds": "Refunds", "foot_contact": "Contact",
    "todo": "to fill",
    "card_sources": "Sources collected", "card_partial": "partial", "card_evidence": "Evidence links", "card_gaps": "Gaps",
    "card_more": "and more", "card_dossier": "Dossier", "card_detailed": "Detailed report", "card_compiled": "Compiled",
    "card_headless": "built by <code>run_job.py</code>, no human in the loop; no Ahrefs in that run",
    "card_manual": "agents orchestrated by hand", "card_none": "Examples are being compiled.",
    "reports_english": "Reports are written in English.",
}

FREE = [
    ("Company website", "home, pricing, features, about, integrations: headlines, CTAs, offers, prices, claims"),
    ("Pricing page, both billing modes", "monthly and yearly plan prices, the default toggle"),
    ("Wayback Machine", "home and pricing 3, 6, 9 and 12 months ago: what changed"),
    ("Sitemaps", "page inventory by type: templates, blog, comparison pages"),
    ("Blog and content hubs", "cadence, topics, funnel stage, length, CTAs, bylines (counted, not named)"),
    ("Changelog and release notes", "release cadence and product focus"),
    ("Page HTML and tag manager", "ad pixels and martech stack"),
    ("Certificate transparency (crt.sh, Cert Spotter)", "subdomains: new products, tools, campaigns"),
    ("GitHub", "public repos, SDKs, developer activity"),
    ("LinkedIn public company page", "team-size proxy, size band, HQ, parent company"),
    ("Social profiles and YouTube", "channels, cadence, video themes"),
    ("Job boards", "open roles by the board's own department labels and by city"),
    ("Reddit, Hacker News, Product Hunt", "community mentions and sentiment"),
    ("Google News", "press coverage"),
    ("Ad libraries: Google, Meta, LinkedIn, Microsoft, TikTok", "ad counts, creatives, themes"),
    ("Review sites: G2, Trustpilot, Capterra", "official rating and count, praise and complaint themes"),
    ("App marketplaces", "listings, ratings, installs, partner programs"),
    ("Public email archives", "newsletter subjects, themes, offers"),
    ("Press releases and investor statements", "leadership, funding, M&A, pricing changes"),
    ("Web search", "creator videos, affiliate terms, best-of lists"),
]
PAID = [
    ("Ahrefs API", "organic and paid keywords, top pages, 24-month history, backlinks, SERPs for money searches, keyword gap", "about 25-30k API units"),
    ("SimilarWeb via RapidAPI", "visits, channel mix, countries, AI referrals", "1 call, cached 45 days"),
    ("OpenAI, Gemini, xAI APIs", "AI visibility: the same 10 buyer questions asked to each model with web search", "about 10 calls per model"),
]
PAID_HEAD = ("Tool", "What it adds", "Per company")
GATES = [("Q", "a quote that is not word for word in the cited source"),
         ("N", "a number that does not appear in the cited source, including small counts like \"73 open roles\""),
         ("W", "a window or basis trap: a partial month, mention order read as rank, an ad count without its time window"),
         ("T", "tone that implies intent (\"misleading\", \"deceptive\")"), ("D", "dashes, hype words, broken characters")]
DOSSIER = ["Passport: 12 facts, each cited or marked not public", "Bottom line and top moves", "Who they sell to, by segment level",
           "How they market: motion, effort by channel, ad libraries", "What they say: pillars, proof, claim check",
           "How they make money: every public plan on one price ladder, monthly and yearly", "Momentum: 90 days against the 90 before",
           "What others say: reviews, media, creators, AI assistants", "Strengths and weaknesses", "What it means for you"]

HOME = {
    "title": "Marketing OSINT",
    "description": "Open-source marketing OSINT: a cited dossier on how any company markets itself, built from up to {n_src} public and optional paid sources.",
    "kicker": "{name} · open source · AGPL-3.0",
    "h1": 'See how any company markets itself. <span class="hl">Every claim one click from its source.</span>',
    "lede": ("Give it a domain. It reads up to {n_src} sources, from the pricing page and the Wayback Machine to ad libraries, job boards, "
             "review sites and what AI assistants answer, then writes a company dossier and a detailed evidence report. Two fact-check "
             "gates run before a page is built. A source it cannot reach is shown as a gap, never guessed."),
    "cta_examples": "See the examples", "cta_order": "Order a report", "cta_run": "Run it yourself", "cta_github": "Source on GitHub",
    "ex_h": "Examples",
    "ex_sub": ("Four companies that are active on almost every channel, compiled on 22 November 2026. Three were orchestrated by hand; "
               "Linear was built by one command with no human in the loop. Gaps are left visible on purpose."),
    "get_h": "What you get", "get_dossier": "The company dossier", "get_plus": "Plus",
    "get_list": ["<b>Detailed report</b> with charts and every evidence link: traffic, paid and organic search, AI visibility, content engine, affiliates and media, momentum, timeline.",
                 "<b>Raw AI answers</b>: the exact questions and answers behind every AI-visibility number.",
                 "<b>Compare</b> 2 or 3 companies: themes heat map, head to head, white space.",
                 "<b>Monitor</b>: rerun later and see what changed since the last run.",
                 "<b>Paid-tools footer</b>: what each run cost, per tool."],
    "how_h": "How it works",
    "steps": [("Collect", "16 script collectors and 2 agent collectors run in parallel. Each writes one JSON file per source in a shared contract: text, verbatim quote, URL, date."),
              ("Synthesize", "An agent turns the files into one analysis. Every sentence carries its evidence; counts come from collector data, never from a hand tally."),
              ("Gate", "A deterministic checker must report 0 issues."),
              ("Fact-check", "A second agent opens the live pages behind the claims the gate lists: headline numbers, prices, the passport, superlatives and anything about deals, funding or leadership."),
              ("Build", "Static HTML pages with numbered citations, light and dark mode. Host them anywhere.")],
    "gate_h": "What the gate blocks",
    "caught_h": "What the live fact-check caught in the examples",
    "caught_sub": "Every draft had passed the gate with 0 issues. The second check, on live pages, still found these:",
    "caught": ["<b>A stale fact.</b> The Miro draft called the Bending Spoons deal \"announced\". The <a href=\"https://via.tt.se/pressmeddelande/4615804/bending-spoons-completes-the-acquisition-of-miro?lang=en\">acquirer's own release</a> shows it closed on 26 October 2026.",
               "<b>A number the data did not reproduce.</b> The Notion draft gave a count of open sales roles that a recount of the job listings did not match. Counts now come from the collector, and the gate checks them.",
               "<b>A missing basis.</b> Plan prices were shown without saying the pricing page loads on yearly billing. A pricing collector now switches the toggle and records both.",
               "<b>A claim true only in a narrower split.</b> \"Most cited site in AI answers\" held across all prompts, but not always on the prompts that do not name the brand."],
    "caught_end": "Every fix went back through the gate before the pages were built.",
    "src_h": "Sources",
    "src_sub": "Public data only: no logins, no sign-ups, no form submissions, no CAPTCHA or bot-protection bypass. People appear by role; bylines and creators are counted, not named.",
    "src_free": "Free", "src_paid": "Paid, all optional",
    "src_end": "No key, no account: that source becomes a gap in the report. Every paid call is logged and shown in the report footer.",
    "reader_h": "Written for you, if you want",
    "reader_p": ("Add a reader profile: your company name, public prices, ideal-customer criteria, marketing teams and house rules. "
                 "The dossier then adds a battlecard, a price check and \"What it means for\" your company, framed by how the company "
                 "relates to you: competitor, benchmark, potential client, partner or your own company. Without a profile the report stays neutral."),
    "run_h": "Run it yourself",
    "run_sub": "Python 3.11+ and Claude Code. One command builds a report end to end; about 35 to 90 minutes per company.",
    "run_src": "Source code:", "run_src_none": "Source code: link comes with the public release",
    "order_band_h": "Rather not run it yourself?",
    "order_band_p": "Order one report. You pay once, we run the pipeline and both checks, and you get a private link by email within {turnaround_days} business days.",
    "fine_h": "Fine print",
    "fine": ["Example reports describe public information about real companies. {name} is not affiliated with, endorsed by or sponsored by them; their names and marks belong to their owners.",
             "Figures are as published by each source on the compile date. Traffic and keyword numbers are third-party estimates.",
             "Some sites block automated readers. We do not bypass that: the report shows the gap."],
}

ORDER = {
    "form": {
        "h": "Order", "domain": "Company website", "domain_ph": "example.com",
        "rel": "How the company relates to you",
        "rels": [("competitor", "Competitor"), ("benchmark", "Benchmark (worth learning from)"), ("prospect", "Potential client"),
                 ("partner", "Partner"), ("self", "My own company")],
        "notes": "Anything we should know (optional)", "notes_ph": "Old names, sibling domains, main competitors",
        "email": "Your email (the private link goes here)",
        "consent": 'I agree to the <a href="terms.html">Terms</a>, have read the <a href="privacy.html">Privacy notice</a>, and ask you to start work at once: I understand I lose the right of withdrawal once the report is delivered.',
        "submit": "Continue to payment", "after": "Next you pay on the {payment_provider} page; the amount is shown there in hryvnias.",
        "errors": {"domain": "Check the company website: enter a domain like example.com.",
                   "relationship": "Choose how the company relates to you.", "email": "Check your email address.",
                   "consent": "Please tick the box to agree to the terms.", "form": "The form could not be sent. Please try again.",
                   "config": "Ordering is paused for a moment. Please write to {contact_email}.",
                   "payment": "The payment page did not open. Please try again in a minute or write to {contact_email}."},
    },
    "pay_with_fields": "On the {payment_provider} payment page you enter the company's website, how it relates to you, and anything we should know, and your email.",
    "pay_without_fields": "You pay on the {payment_provider} payment page. Then reply to the receipt, or write to {contact_email}, with the company's website, how it relates to you, and anything we should know.",
    "title": "Order a report",
    "description": "Pay once and get a cited marketing dossier on one company, delivered by private link.",
    "h1": "One company. One report. <span class=\"hl\">Delivered by private link.</span>",
    "lede": "Tell us which company you want to understand. We build the dossier and the detailed evidence report, run both fact-checks, and email you a private link.",
    "price_label": "Price", "price_note": "one-off payment, {tax_note}",
    "turn_label": "Delivery", "turn_value": "within {turnaround_days} business days",
    "link_label": "Link", "link_value": "private, kept for {link_ttl_days} days",
    "buy": "Pay and order", "buy_missing": "Payment link not set yet",
    "consent": 'By paying you agree to the <a href="terms.html">Terms</a> and confirm you have read the <a href="privacy.html">Privacy notice</a> and the <a href="refunds.html">Refund policy</a>.',
    "steps_h": "How it works",
    "steps": [("You pay", "On the {payment_provider} checkout page you enter the company's website, how it relates to you, and anything we should know. {payment_provider} asks for your email."),
              ("We build", "We run the collectors, the synthesis, the automatic gate and the live fact-check. A source we cannot reach is listed as a gap."),
              ("You read", "You get an email with a private link to the dossier, the detailed report and the raw AI answers.")],
    "get_h": "What is in the report",
    "get": ["The company dossier: passport, bottom line, who they sell to, how they market, what they say, how they make money, momentum, what others say, strengths and weaknesses.",
            "\"What it means for you\", framed by the relationship you choose: competitor, benchmark, potential client, partner or your own company.",
            "The detailed report with charts and every evidence link, and the raw answers behind the AI-visibility numbers.",
            "A list of gaps: the sources that could not be read, and why."],
    "sources_h": "Sources used in paid reports",
    "sources_p": "Public sources from the list on the home page, the pricing page in both billing modes, and AI answers from {ai_models}. {seo_note}",
    "not_h": "What we do not do",
    "not": ["Reports on private individuals.", "Logging in, signing up or getting past bot protection on any site.",
            "Promises about numbers we cannot see: traffic and keyword figures are third-party estimates, and they are labelled as such."],
    "faq_h": "Questions",
    "faq": [("Who can open the link?", "Anyone who has it. It is long and random, it is not linked from anywhere and search engines are told not to index it. Share it only with people you want to read the report."),
            ("Can I see an example first?", 'Yes: the <a href="{home}#examples">four example reports</a> were built with the same pipeline.'),
            ("What if the report comes out thin?", 'Some companies block most automated readers. If too few sources can be read, we tell you and refund in full. See the <a href="refunds.html">Refund policy</a>.'),
            ("Do you store my data?", 'We keep no database. Your order lives in {payment_provider}, the report lives at its link for {link_ttl_days} days. Details in the <a href="privacy.html">Privacy notice</a>.')],
}

THANKS = {
    "p_details": "Not sent the company details yet? Write to {contact_email} with the company's website, how it relates to you, and anything we should know.",
    "title": "Thank you", "description": "Payment received.",
    "h1": "Thank you. Your order is in.",
    "p": ["{payment_provider} has sent you a receipt by email.",
          "We will email the private link to the address you gave at checkout within {turnaround_days} business days.",
          "If the email does not arrive, check spam, then write to {contact_email}."],
    "back": "Back to the home page",
}

LEGAL_INTRO = "Last updated {legal_updated}. This page is a plain-language draft; it is not legal advice."

TERMS = {
    "title": "Terms of Service", "description": "Terms for ordering a marketing OSINT report.",
    "sections": [
        ("Who we are", "These terms are between you and {seller_name} ({seller_legal}), {seller_address}, {seller_country} (\"we\"). Contact: {contact_email}."),
        ("The service", "For a one-off payment we prepare one report about one company that you name by its website. The report is built from public sources and from the tools listed on the order page, checked by an automatic gate and a fact-check on live pages, written in English, and delivered as a private link by email within {turnaround_days} business days of payment. The service is marketing research for businesses and organisations; it is not offered for personal use."),
        ("Ordering and payment", "You order and pay through {payment_provider}. The price is shown on the order page ({price}, {tax_note}). {payment_provider} processes your card; we never see your card details. {payment_provider} sends you a receipt.{mor_note}"),
        ("What you give us", "The website of a company, how it relates to you, optional notes, and your email address. The subject of a report must be a business. We may refuse an order, with a full refund, when the subject is a private individual, when the purpose appears unlawful, or when we cannot read enough of the company's public sources."),
        ("Delivery and the link", "The report is delivered as a long random link. Anyone who has the link can open it, so keep it private. The link stays available for {link_ttl_days} days and is then deleted. Save the pages if you need them for longer."),
        ("Accuracy", "The report describes public information as it stood on the compile date. Traffic, keyword and ad figures are estimates from third parties. Sources that block automated readers are shown as gaps. The report is marketing research, not legal, financial or investment advice, and we do not guarantee that it is complete or error free."),
        ("Your use of the report", "You may use the report inside your own organisation. You may not resell it or publish it as a whole. Company names and trademarks in the report belong to their owners; we are not affiliated with the companies we describe."),
        ("Right of withdrawal", "If you are a consumer in the EU or the UK, you have a 14-day right of withdrawal for services. By paying you ask us to start work at once and you acknowledge that you lose the right of withdrawal once the report has been delivered. If you withdraw before delivery, we refund you in full. See the Refund policy."),
        ("Liability", "To the extent the law allows, our total liability for an order is limited to the price you paid for it. Nothing in these terms limits liability that cannot be limited by law."),
        ("Open source", "The software that builds the reports is open source under the GNU Affero General Public License v3.0. These terms cover the paid service, not the software."),
        ("Changes and law", "We may update these terms; the version on this page when you pay applies to your order. These terms are governed by the law of {governing_law}."),
        ("Complaints", "Write to {contact_email}. We answer within 14 days. You can also contact the consumer protection authority where you live."),
    ],
}

PRIVACY = {
    "title": "Privacy notice", "description": "What personal data the order service uses and why.",
    "sections": [
        ("Controller", "{seller_name} ({seller_legal}), {seller_address}, {seller_country}. Contact for privacy questions: {contact_email}."),
        ("What we collect", "When you order: your email address, your name and billing details as {payment_provider} collects them, the company website you name, the relationship you choose and any notes. We do not see or store card numbers."),
        ("Rules we follow", "The Law of Ukraine \"On Personal Data Protection\" and, for people in the European Union or the UK, the GDPR and the UK GDPR."),
        ("Transfers abroad", "Our processors may handle data outside your country, including in the United States. We use providers that offer standard contractual clauses or an equivalent safeguard."),
        ("Why", "To deliver the report you ordered and to answer you (contract), and to keep payment records as tax law requires (legal obligation)."),
        ("Where it is kept", "We run no database of our own. Order details are kept in our {payment_provider} account. The email with your link is kept in our mailbox. The report itself is kept at its private link for {link_ttl_days} days and then deleted."),
        ("Who processes it for us", "{payment_provider} (payments and receipts), {email_provider} (email), {hosting_provider} (hosting of the site and the report links). To build the report, AI providers ({ai_models}) receive the company website and public data about that company, not your personal data."),
        ("How long", "Payment records: as long as tax law requires, in {payment_provider}. Emails: up to {email_retention}. Report links: {link_ttl_days} days."),
        ("Your rights", "You can ask for access, correction, deletion, restriction or a copy of your data, and object to processing, by writing to {contact_email}. You can also complain to your data protection authority."),
        ("Cookies and tracking", "This site sets no cookies and runs no analytics. Fonts and pages are served from this site through {hosting_provider}, which processes your IP address to deliver them. The payment page of {payment_provider} has its own privacy notice."),
        ("The companies in our reports", "Reports describe businesses from public sources. People appear only by role, except company leaders named in public announcements. To ask about something in a report, write to {contact_email}."),
    ],
}

REFUNDS = {
    "title": "Refund policy", "description": "When you get your money back.",
    "sections": [
        ("Full refund", "We refund you in full if we cannot deliver within {turnaround_days} business days, if we refuse the order (see the Terms), or if you withdraw before the report is delivered."),
        ("Thin report", "If the company blocks so many automated readers that fewer than {min_sources} sources can be read, we tell you before delivery and refund you in full, or deliver the report at your choice."),
        ("Errors", "If you find a factual error that changes a conclusion, tell us within 14 days of delivery. We correct the report and send a new link; if we cannot, we refund you."),
        ("After delivery", "Once the report has been delivered, the payment is not refundable for a change of mind, except where the law gives you a right to a refund."),
        ("How to ask", "Write to {contact_email} with the email you paid with. Refunds go back to the original payment method through {payment_provider}, usually within 5 to 10 business days."),
    ],
}

CONTACT = {
    "title": "Contact", "description": "Who runs the order service and how to reach us.",
    "sections": [
        ("Seller", "{seller_name} ({seller_legal})<br>{seller_address}<br>{seller_country}"),
        ("Email", "{contact_email}"),
        ("Registration", "{registration}"),
    ],
}
