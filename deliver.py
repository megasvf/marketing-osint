"""Deliver a paid report by private link, and remove links that have expired. No database: the link lives in the
email you send, the expiry date lives next to the report.

  python deliver.py example.com --email buyer@example.org [--lang en|uk] [--order "payment or invoice id"]
  python deliver.py --purge            # delete delivered reports whose expiry date has passed
  python deliver.py --list             # show delivered reports and their expiry dates

What it does: copies output/<domain>/ (build it first with run_job.py) to public/r/<random token>/, writes the expiry
date (site/business.json link_ttl_days) to public/r/<token>/.expires, and prints the link and a ready email. Then deploy
public/ as usual. robots.txt (written by site/build_site.py) disallows /r/, every report page carries noindex, and the
token is 22 random URL-safe characters, so the page is reachable only through the link.
"""
import argparse
import json
import secrets
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
R = ROOT / "public" / "r"

EMAIL = {
    "en": ("Your Marketing OSINT report: {company}",
           "Hello,\n\nyour report on {company} ({domain}) is ready:\n\n{url}\n\n"
           "The dossier opens first; the detailed report with every evidence link and the raw AI answers are linked at the top.\n"
           "Anyone with this link can open the report, so share it only with people you want to read it. "
           "It stays available until {expires}.\n\n"
           "If something looks wrong, reply to this email within 14 days and we will check it.\n\n"
           "Thank you,\n{seller}"),
    "uk": ("Ваш звіт Marketing OSINT: {company}",
           "Вітаю!\n\nВаш звіт про {company} ({domain}) готовий:\n\n{url}\n\n"
           "Першим відкривається досьє; детальний звіт з усіма посиланнями на докази й сирі відповіді AI-асистентів є вгорі сторінки.\n"
           "Звіт відкриє будь-хто, у кого є це посилання, тож діліться ним лише з тими, хто має його читати. "
           "Посилання працюватиме до {expires}. Сам звіт написаний англійською.\n\n"
           "Якщо щось виглядає неправильно, відповідайте на цей лист протягом 14 днів, і ми перевіримо.\n\n"
           "Дякуємо,\n{seller}"),
}


def business():
    f = ROOT / "site" / "business.json"
    return json.loads((f if f.exists() else ROOT / "site" / "business.example.json").read_text(encoding="utf-8"))


def deliver(domain, email, lang, order):
    src = ROOT / "output" / domain
    if not (src / "index.html").exists():
        sys.exit(f"output/{domain}/index.html not found: run run_job.py {domain} first")
    b = business()
    ttl = int(b.get("link_ttl_days") or 90)
    token = secrets.token_urlsafe(16)
    dst = R / token
    shutil.copytree(src, dst)
    sys.path.insert(0, str(ROOT))
    from design import brand as BR
    for f in dst.glob("*.html"):  # private pages: no referrer, and fonts from our own host when configured
        h = f.read_text(encoding="utf-8").replace("<head>", '<head><meta name="referrer" content="no-referrer">', 1)
        if (b.get("self_host_fonts") or "yes") == "yes":
            h = BR.self_host_fonts(h)
        f.write_text(h, encoding="utf-8")
    expires = (date.today() + timedelta(days=ttl)).isoformat()
    (dst / ".expires").write_text(json.dumps({"expires": expires, "domain": domain, "order": order}), encoding="utf-8")
    site = (b.get("site_url") or "https://YOUR-SITE").rstrip("/")
    url = f"{site}/r/{token}/"
    a = json.loads((ROOT / "data" / domain / "analysis.json").read_text(encoding="utf-8"))
    subject, body = EMAIL[lang]
    v = {"company": a.get("company") or domain, "domain": domain, "url": url, "expires": expires,
         "seller": b.get("seller_name") or "Marketing OSINT"}
    print(f"delivered: {dst}\nlink: {url}\nexpires: {expires}\n\nTo: {email}\nSubject: {subject.format(**v)}\n\n{body.format(**v)}\n")
    print("Next: deploy public/ (for example `npx wrangler pages deploy public`), open the link once to check it, then send the email.")


def purge(dry=False):
    today = date.today().isoformat()
    for d in sorted(R.glob("*/")) if R.exists() else []:
        meta = json.loads((d / ".expires").read_text(encoding="utf-8")) if (d / ".expires").exists() else {"expires": "0000"}
        expired = meta["expires"] < today
        print(f"{'EXPIRED ' if expired else ''}{d.name[:6]}…  {meta.get('domain', '?')}  until {meta['expires']}")
        if expired and not dry:
            shutil.rmtree(d)
    if not dry:
        print("purged expired reports; deploy public/ so they disappear from the host too")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("domain", nargs="?")
    ap.add_argument("--email", default="")
    ap.add_argument("--lang", default="en", choices=["en", "uk"])
    ap.add_argument("--order", default="")
    ap.add_argument("--purge", action="store_true")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.purge or a.list:
        return purge(dry=a.list)
    if not a.domain:
        ap.error("domain is required")
    deliver(a.domain, a.email, a.lang, a.order)


if __name__ == "__main__":
    main()
