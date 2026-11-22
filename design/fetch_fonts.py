"""Download the three font families once into design/fonts/ so the site can serve them itself (no Google request,
no visitor IP sent to Google). Latin, Latin Extended, Cyrillic and Cyrillic Extended subsets only.

  python design/fetch_fonts.py

Fonts: Inter, Source Serif 4, JetBrains Mono, all under the SIL Open Font License 1.1 (redistribution allowed).
"""
import re
from pathlib import Path

import requests

OUT = Path(__file__).resolve().parent / "fonts"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
FAMILIES = ["Inter:wght@400;500;600;700", "Source+Serif+4:opsz,wght@8..60,600;8..60,700", "JetBrains+Mono:wght@500;600"]
KEEP = {"latin", "latin-ext", "cyrillic", "cyrillic-ext"}
LICENSES = [("inter", "https://raw.githubusercontent.com/rsms/inter/master/LICENSE.txt"),
            ("sourceserif", "https://raw.githubusercontent.com/adobe-fonts/source-serif/release/LICENSE.md"),
            ("jetbrains", "https://raw.githubusercontent.com/JetBrains/JetBrainsMono/master/OFL.txt")]


def main():
    OUT.mkdir(exist_ok=True)
    css_out, n = [], 0
    for fam in FAMILIES:
        css = requests.get(f"https://fonts.googleapis.com/css2?family={fam}&display=swap", headers={"User-Agent": UA}, timeout=30)
        css.raise_for_status()
        for subset, block in re.findall(r"/\* ([\w-]+) \*/\s*(@font-face\s*{[^}]*})", css.text):
            if subset not in KEEP:
                continue
            url = re.search(r"url\((https://[^)]+\.woff2)\)", block).group(1)
            name = re.sub(r"[^\w.-]", "_", url.split("/s/")[1])
            f = OUT / name
            if not f.exists():
                f.write_bytes(requests.get(url, headers={"User-Agent": UA}, timeout=30).content)
                n += 1
            css_out.append(f"/* {subset} */\n" + block.replace(url, name))
    (OUT / "fonts.css").write_text("\n".join(css_out) + "\n", encoding="utf-8")
    lic = ["Inter, Source Serif 4 and JetBrains Mono are distributed in this folder under the SIL Open Font License, Version 1.1.\n"
           "Each family's copyright notice and the full license text follow.\n"]
    for name, url in LICENSES:
        lic.append(f"==== {name} ====\n\n" + requests.get(url, headers={"User-Agent": UA}, timeout=30).text.strip() + "\n")
    (OUT / "LICENSE.txt").write_text("\n\n".join(lic), encoding="utf-8")
    print(f"{len(css_out)} @font-face rules, {n} files downloaded -> {OUT}")


if __name__ == "__main__":
    main()
