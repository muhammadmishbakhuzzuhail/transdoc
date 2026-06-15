"""Run PaddleOCR PP-StructureV3 in the isolated paddle interpreter and write structured
regions as JSON. Companion to subprocess_detect.py (plain layout) — this one also returns each
region's CONTENT: OCR text for prose, **LaTeX for formulas**, **HTML for tables**, plus the
reading order. See ppstructurev3-region-router.

    <paddle-python> -m transdoc.layout.structure_detect <pdf> <out.json> <pno> [<pno> ...]

Output: ``{pno: [{label, bbox:[x0,y0,x1,y1] in points, content, order}]}`` (out.json, not
stdout — paddle pollutes stdout). bbox is scaled from the render dpi back to PDF points.
"""

from __future__ import annotations

import json
import sys


def _regions_for_page(pipe, page) -> list[dict]:
    from .structure import parse_regions, render_page_array

    arr, scale = render_page_array(page)   # downscaled to fit GPU; scale maps px -> points
    res = list(pipe.predict(arr))
    return parse_regions(res[0].json, scale) if res else []


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        sys.stderr.write("usage: structure_detect <pdf> <out.json> <pno> [<pno> ...]\n")
        return 2
    pdf_path, out_path = argv[0], argv[1]
    pnos = [int(x) for x in argv[2:]]

    import fitz
    from paddleocr import PPStructureV3

    pipe = PPStructureV3()
    doc = fitz.open(pdf_path)
    try:
        result = {pno: _regions_for_page(pipe, doc[pno]) for pno in pnos}
    finally:
        doc.close()
    with open(out_path, "w") as fh:
        json.dump(result, fh)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
