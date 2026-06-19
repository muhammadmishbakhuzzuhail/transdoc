# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Compare formatting-feature preservation between an original PDF and its translation.

Extracts per-page span features (count, bold, italic, coloured, font sizes) from both files
and prints them side by side, so you can see which features the overlay carried over. Useful
after the LAYOUT overlay, where the translated text is real selectable text.

Honest scope: the overlay applies ONE style per (reflowed) block, so word-level emphasis
(a single bold/italic/coloured word inside a paragraph) cannot survive — only block-dominant
styling does. This tool makes that visible rather than hiding it.

    .venv/bin/python scripts/compare_features.py original.pdf translated.pdf [--pages 1]
"""

from __future__ import annotations

import argparse


def page_features(page) -> dict:
    bold = ital = color = n = 0
    sizes: dict[float, int] = {}
    for blk in page.get_text("dict").get("blocks", []):
        for line in blk.get("lines", []):
            for sp in line.get("spans", []):
                if not sp.get("text", "").strip():
                    continue
                n += 1
                fl = sp.get("flags", 0)
                if fl & 2 ** 4:
                    bold += 1
                if fl & 2 ** 1:
                    ital += 1
                if sp.get("color", 0) != 0:
                    color += 1
                s = round(sp.get("size", 0), 1)
                sizes[s] = sizes.get(s, 0) + 1
    top = sorted(sizes, reverse=True)[:4]
    return {"spans": n, "bold": bold, "italic": ital, "colored": color, "sizes": top}


def main() -> None:
    import fitz

    ap = argparse.ArgumentParser()
    ap.add_argument("original")
    ap.add_argument("translated")
    ap.add_argument("--pages", type=int, default=1, help="how many leading pages to compare")
    args = ap.parse_args()

    o, t = fitz.open(args.original), fitz.open(args.translated)
    npages = min(args.pages, o.page_count, t.page_count)
    print(f"{'feature':9} {'ORIGINAL':>10} {'TRANSLATED':>11}   note")
    print("-" * 52)
    agg_o = {"spans": 0, "bold": 0, "italic": 0, "colored": 0}
    agg_t = {"spans": 0, "bold": 0, "italic": 0, "colored": 0}
    for p in range(npages):
        fo, ft = page_features(o[p]), page_features(t[p])
        for k in agg_o:
            agg_o[k] += fo[k]
            agg_t[k] += ft[k]
    for k in ("spans", "bold", "italic", "colored"):
        ov, tv = agg_o[k], agg_t[k]
        note = ""
        if k in ("bold", "italic", "colored") and ov:
            ratio = tv / ov
            note = ("over-applied" if ratio > 1.5 else
                    "mostly lost" if ratio < 0.4 else "carried")
        print(f"{k:9} {ov:10} {tv:11}   {note}")
    print("\nnote: spans drop is expected (translation reflows words into fewer runs);")
    print("word-level emphasis can't survive a block-level overlay — only block-dominant style.")


if __name__ == "__main__":
    main()
