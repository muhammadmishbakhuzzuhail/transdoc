"""Reproducible output-fidelity QA. For each output PDF it flags, per page:
  - OVERWRITE: a text span whose bbox overlaps an embedded image (raster/crop) — text drawn
    on top of a figure/table crop ("menimpa tidak rapi").
  - TINY:      a span rendered < 6 pt (illegible).
  - OVERFLOW:  a span whose bbox leaves the page rect.
  - coverage:  per-page text-span count, image count, mean font size.
Run: python scripts/qa_fidelity.py out/<file>.pdf [more.pdf ...]
No torch/paddle needed — pure PyMuPDF geometry. This makes the review repeatable instead of
eyeballed."""

from __future__ import annotations

import sys

import fitz


def _overlap(a: fitz.Rect, b: fitz.Rect) -> float:
    inter = a & b
    if not inter or a.is_empty:
        return 0.0
    return abs(inter) / max(abs(a), 1e-6)


def audit(path: str) -> dict:
    d = fitz.open(path)
    findings = {"overwrite": [], "tiny": [], "overflow": [], "pages": []}
    for pno in range(d.page_count):
        page = d[pno]
        pr = page.rect
        imgs = [fitz.Rect(b["bbox"]) for b in page.get_image_info(xrefs=False)]  # placements
        sizes = []
        nspans = 0
        for blk in page.get_text("dict")["blocks"]:
            for line in blk.get("lines", []):
                for sp in line.get("spans", []):
                    txt = sp["text"].strip()
                    if not txt:
                        continue
                    nspans += 1
                    r = fitz.Rect(sp["bbox"])
                    sizes.append(sp["size"])
                    # text over an image (covering >35% of the span)
                    for ir in imgs:
                        if _overlap(r, ir) > 0.35:
                            findings["overwrite"].append((pno + 1, round(sp["size"], 1), txt[:50]))
                            break
                    if sp["size"] < 6.0:
                        findings["tiny"].append((pno + 1, round(sp["size"], 1), txt[:50]))
                    if r.x0 < pr.x0 - 1 or r.y0 < pr.y0 - 1 or r.x1 > pr.x1 + 1 or r.y1 > pr.y1 + 1:
                        findings["overflow"].append((pno + 1, txt[:50]))
        findings["pages"].append({
            "page": pno + 1, "spans": nspans, "images": len(imgs),
            "font_mean": round(sum(sizes) / len(sizes), 1) if sizes else 0,
            "font_min": round(min(sizes), 1) if sizes else 0,
        })
    d.close()
    return findings


def main() -> None:
    for path in sys.argv[1:]:
        f = audit(path)
        print(f"\n{'='*70}\n{path}")
        ow, tn, of = f["overwrite"], f["tiny"], f["overflow"]
        print(f"  OVERWRITE (text on image): {len(ow)}   TINY (<6pt): {len(tn)}   "
              f"OVERFLOW: {len(of)}")
        for tag, items in (("OVERWRITE", ow), ("TINY", tn)):
            for it in items[:8]:
                print(f"    [{tag}] p{it[0]} {it[1]}pt  {it[2]!r}")
            if len(items) > 8:
                print(f"    ... +{len(items)-8} more")
        for it in of[:5]:
            print(f"    [OVERFLOW] p{it[0]} {it[1]!r}")
        # page coverage summary
        dense = [p for p in f["pages"] if p["font_min"] and p["font_min"] < 6]
        print(f"  pages={len(f['pages'])}  pages_with_subpt_font={len(dense)}")


if __name__ == "__main__":
    main()
