"""Brand constants shared by every page: name, tagline, fonts, logo, tokens. See DESIGN.md.

Rename the project here only: every page reads NAME from this file.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent

NAME = "Marketing OSINT"
TAGLINE = "See how any company markets itself, from public data"

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700'
         '&family=Source+Serif+4:opsz,wght@8..60,600;8..60,700&family=JetBrains+Mono:wght@500;600&display=swap" rel="stylesheet">')

TOKENS = (HERE / "tokens.css").read_text(encoding="utf-8")

# The mark: a dark tile with a teal lens set off-centre: looking at a company from the outside.
LOGO = ('<svg class="logo" viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">'
        '<rect width="24" height="24" rx="6" fill="var(--ink)"/>'
        '<circle cx="14.5" cy="9.5" r="5" fill="var(--brand)"/>'
        '<rect x="5" y="16" width="9" height="2.5" rx="1.25" fill="var(--bg)"/></svg>')

FAVICON = ('<link rel="icon" href="data:image/svg+xml,'
           '%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 24 24%22%3E'
           '%3Crect width=%2224%22 height=%2224%22 rx=%226%22 fill=%22%2316181d%22/%3E'
           '%3Ccircle cx=%2214.5%22 cy=%229.5%22 r=%225%22 fill=%22%230b6b66%22/%3E'
           '%3Crect x=%225%22 y=%2216%22 width=%229%22 height=%222.5%22 rx=%221.25%22 fill=%22%23fff%22/%3E%3C/svg%3E">')

HEAD = FONTS + FAVICON

# Self-hosted fonts (design/fetch_fonts.py -> design/fonts/, served at /fonts/): no request to Google from the page.
SELF_FONTS = '<link rel="stylesheet" href="/fonts/fonts.css">'
FONT_DIR = HERE / "fonts"


def self_host_fonts(html):
    """Swap the Google Fonts links for the self-hosted stylesheet (site deploys and delivered reports)."""
    return html.replace(FONTS, SELF_FONTS)

# Public repository URL, linked from the site navigation, hero and footer.
REPO_URL = "https://github.com/megasvf/marketing-osint"
