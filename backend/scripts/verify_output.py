# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Verify a generated PDF actually renders readable target-language text — by OCR'ing the
rendered pixels, not trusting block counts.

The lesson behind this tool: "translated N/N blocks" is an IR-level claim. The overlay can
still ship illegibly-shrunk or cache-poisoned text. OCR'ing the rendered page is an objective
check of what a human would actually see.

    .venv/bin/python scripts/verify_output.py out/review/form.id.pdf --lang id

Reports, per page: OCR confidence, target- vs source-language marker counts, and a verdict.
Exits non-zero if any page looks wrong (low confidence or source-language text leaking).
"""

from __future__ import annotations

import argparse
import io
import sys

# Cheap stop-word markers per language to tell "is this really lang X" without a model.
MARKERS = {
    "id": ["yang", "dan", "adalah", "untuk", "dengan", "dari", "ini", "pada"],
    "en": ["the", "and", "is", "for", "with", "of", "this", "are"],
    "es": ["que", "los", "para", "con", "una", "del"],
    "fr": ["les", "des", "une", "pour", "avec", "dans"],
    "de": ["und", "der", "die", "das", "für", "mit", "ist"],
}


def _markers(text: str, lang: str) -> int:
    t = f" {text.lower()} "
    return sum(t.count(f" {w} ") for w in MARKERS.get(lang, []))


def verify(path: str, lang: str, source: str = "en", dpi: int = 200) -> bool:
    import fitz
    import pytesseract
    from PIL import Image

    doc = fitz.open(path)
    ok = True
    print(f"{path}  (target={lang})")
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=dpi)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        data = pytesseract.image_to_data(img, lang="ind+eng",
                                         output_type=pytesseract.Output.DICT)
        confs = [float(c) for c in data["conf"] if float(c) > 0]
        words = [w for w, c in zip(data["text"], data["conf"]) if w.strip() and float(c) > 40]
        avg = sum(confs) / len(confs) if confs else 0
        text = " ".join(words)
        tgt_m, src_m = _markers(text, lang), _markers(text, source)
        bad = avg < 60 or (src_m > 2 and src_m >= tgt_m)
        ok = ok and not bad
        verdict = "BAD" if bad else "ok"
        print(f"  p{i+1}: conf={avg:3.0f} words={len(words):4} "
              f"{lang}-markers={tgt_m:2} {source}-markers={src_m:2}  [{verdict}]")
    return ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--lang", required=True, help="expected target language (ISO)")
    ap.add_argument("--source", default="en", help="source language to flag if it leaks")
    args = ap.parse_args()
    sys.exit(0 if verify(args.pdf, args.lang, args.source) else 1)


if __name__ == "__main__":
    main()
