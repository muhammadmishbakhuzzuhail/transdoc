"""Fetch script-diverse real document images from Wikimedia Commons via the search API.

Wikimedia requires a descriptive User-Agent. Saves into corpus/real/full_image/.
"""

from __future__ import annotations

import os
import ssl
import urllib.parse
import urllib.request
import json

UA = "transdoc-research/0.1 (https://github.com/muhammadmishbakhuzzuhail/translate)"
CTX = ssl.create_default_context()
OUT = "corpus/real/full_image"

TARGETS = {
    "manuscript_arabic": "arabic manuscript page text",
    "document_chinese": "chinese document page calligraphy text",
    "letter_handwritten": "handwritten letter manuscript page",
    "typed_letter": "typewritten letter document",
    "newspaper_scan": "historical newspaper front page",
    "document_hebrew": "hebrew manuscript document page",
    "document_greek": "greek manuscript papyrus text",
    "document_cyrillic": "russian document manuscript page",
}


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return json.load(urllib.request.urlopen(req, timeout=40, context=CTX))


def _fetch(url: str, out: str) -> int:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    data = urllib.request.urlopen(req, timeout=90, context=CTX).read()
    with open(out, "wb") as f:
        f.write(data)
    return len(data)


def search(term: str, n: int = 4) -> list[tuple[str, str]]:
    q = urllib.parse.urlencode({
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f"filetype:bitmap {term}", "gsrnamespace": 6, "gsrlimit": n,
        "prop": "imageinfo", "iiprop": "url|size|mime", "iiurlwidth": 1800,
    })
    d = _get("https://commons.wikimedia.org/w/api.php?" + q)
    out = []
    for p in d.get("query", {}).get("pages", {}).values():
        ii = p.get("imageinfo", [{}])[0]
        u = ii.get("thumburl") or ii.get("url")
        if u and ii.get("mime", "").startswith("image/"):
            out.append((p["title"], u))
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, term in TARGETS.items():
        try:
            results = search(term)
        except Exception as e:
            print(f"search FAIL {name}: {e}")
            continue
        for title, url in results:
            ext = ".png" if ".png" in url.lower() else ".jpg"
            out = f"{OUT}/{name}{ext}"
            try:
                n = _fetch(url, out)
                if n > 5000:
                    print(f"OK   {out} ({n} B)  <- {title[:45]}")
                    break
            except Exception:
                continue
        else:
            print(f"FAIL {name} (no usable result)")


if __name__ == "__main__":
    main()
