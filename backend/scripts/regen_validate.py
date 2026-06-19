# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Regenerate the manual validation set into out_validate/: run the full pipeline on a
representative spread of corpus docs (digital, non-Latin scans, RTL, a form, a docx) and write each
translated output plus side-by-side source/output page-0 PNGs. Visual proof the pipeline is healthy
after the OCR-routing / VRAM fixes. Not a CI gate — eyeball the PNGs.

    .venv/bin/python -m scripts.regen_validate
"""

from __future__ import annotations

from pathlib import Path

import fitz

from transdoc.config import Config, Engine, OutputFormat
from transdoc.pipeline import run

OUT = Path("out_validate")
OUT.mkdir(exist_ok=True)

# (tag, source path, source lang, target, output format)
CASES = [
    ("arxiv",  "corpus/real/digital_text/arxiv_bert_en.pdf", "en", "id", OutputFormat.PDF),
    ("hindi",  "corpus/real/scanned_pdf/udhr_hindi_scan.pdf", "hi", "id", OutputFormat.PDF),
    ("thai",   "corpus/real/scanned_pdf/udhr_thai_scan.pdf",  "th", "id", OutputFormat.PDF),
    ("zh",     "corpus/real/multilingual/udhr_chinese.pdf",   "zh", "id", OutputFormat.PDF),
    ("arabic", "corpus/real/multilingual/udhr_arabic.pdf",    "ar", "id", OutputFormat.PDF),
    ("w9",     "corpus/real/forms/irs_w9_form.pdf",           "en", "id", OutputFormat.PDF),
    ("docx",   "corpus/synthetic/docx/structured.docx",       "en", "id", OutputFormat.DOCX),
]


def _png(pdf_path: str, dst: Path) -> bool:
    try:
        with fitz.open(pdf_path) as d:
            d[0].get_pixmap(dpi=110).save(str(dst))
        return True
    except Exception:
        return False


for tag, src, slang, tgt, fmt in CASES:
    if not Path(src).exists():
        print(f"SKIP {tag} (missing)")
        continue
    ext = ".pdf" if fmt == OutputFormat.PDF else ".docx"
    out = str(OUT / f"{tag}_{tgt}{ext}")
    cfg = Config(source_lang=slang, target_lang=tgt, engine=Engine.GOOGLE, output_format=fmt)
    try:
        r = run(src, cfg, out_path=out)
    except Exception as e:
        print(f"ERR  {tag}: {type(e).__name__}: {e}")
        continue
    # source IN png (PDFs only; docx can't rasterise directly)
    if src.lower().endswith(".pdf"):
        _png(src, OUT / f"cmp_{tag}_IN.png")
    out_png = _png(r.output_path, OUT / f"cmp_{tag}_OUT.png")
    n_tr = sum(1 for b in r.doc.blocks if getattr(b, "translated", None))
    print(f"OK   {tag}: -> {Path(r.output_path).name}  blocks_translated={n_tr}  out_png={out_png}")

print("DONE")
