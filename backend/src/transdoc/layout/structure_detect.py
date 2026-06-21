# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
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


def _detect(pipe, pdf_path: str, out_path: str, pnos: list[int]) -> None:
    import fitz
    doc = fitz.open(pdf_path)
    try:
        result = {pno: _regions_for_page(pipe, doc[pno]) for pno in pnos}
    finally:
        doc.close()
    with open(out_path, "w") as fh:
        json.dump(result, fh)


# Sentinel lines on stdout — paddle pollutes stdout with progress, so the parent ignores any line
# without one of these prefixes. Server mode loads the model ONCE and serves many documents.
_READY = "__STRUCT_READY__"
_OK = "__STRUCT_OK__"
_ERR = "__STRUCT_ERR__"


def _serve(lang: str | None) -> int:
    """Persistent worker: load PP-StructureV3 once, then process one request per stdin line
    ({"pdf","out","pnos"} JSON) until EOF, emitting a sentinel line per request. Lets the parent
    reuse a warm model across documents instead of paying the ~30s cold-load every time."""
    from paddleocr import PPStructureV3
    pipe = PPStructureV3(lang=lang) if lang else PPStructureV3()
    sys.stdout.write(_READY + "\n")
    sys.stdout.flush()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            break
        try:
            req = json.loads(line)
            _detect(pipe, req["pdf"], req["out"], [int(p) for p in req["pnos"]])
            sys.stdout.write(f"{_OK} {req['out']}\n")
        except Exception as e:  # keep the worker alive across a bad request
            sys.stdout.write(f"{_ERR} {str(e)[:300]}\n")
        sys.stdout.flush()
    return 0


def main(argv: list[str]) -> int:
    lang = next((a.split("=", 1)[1] for a in argv if a.startswith("--lang=")), None)
    rest = [a for a in argv if not a.startswith("--lang=")]
    if rest and rest[0] == "--serve":
        return _serve(lang)
    if len(rest) < 3:
        sys.stderr.write("usage: structure_detect <pdf> <out.json> <pno> [<pno> ...] | --serve\n")
        return 2
    pdf_path, out_path = rest[0], rest[1]
    pnos = [int(x) for x in rest[2:]]

    from paddleocr import PPStructureV3
    pipe = PPStructureV3(lang=lang) if lang else PPStructureV3()
    _detect(pipe, pdf_path, out_path, pnos)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
