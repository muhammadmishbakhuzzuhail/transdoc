# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Per-file COMET-Kiwi QE for the example set. Re-runs the pipeline with quality_check=True
(translation hits the TM cache, so it's fast) and prints mean/min QE + % below threshold.
align disabled to keep only one model (COMET) resident on the 6 GB GPU."""
from __future__ import annotations

import sys

from transdoc.config import Config, Engine, OutputFormat
from transdoc.pipeline import run

FILES = [
    ("arabic-pdf",   "corpus/real/multilingual/udhr_arabic.pdf"),
    ("chinese-pdf",  "corpus/real/multilingual/udhr_chinese.pdf"),
    ("thai-pdf",     "corpus/real/multilingual/udhr_thai.pdf"),
    ("hindi-scan",   "corpus/real/scanned_pdf/udhr_hindi_scan.pdf"),
    ("arabic-image", "corpus/real/full_image/manuscript_arabic.jpg"),
    ("mixed-docx",   "corpus/synthetic/docx/structured.docx"),
]

print(f"{'file':14}{'blocks':>7}{'scored':>7}{'mean':>8}{'min':>8}{'%<thr':>7}")
for tag, path in FILES:
    cfg = Config(source_lang="auto", target_lang="en", engine=Engine.GOOGLE,
                 output_format=OutputFormat.SAME, quality_check=True, align_styles=False)
    try:
        res = run(path, cfg, out_path=f"/tmp/qe_{tag}{__import__('pathlib').Path(path).suffix}")
        blocks = [b for b in res.doc.blocks if b.is_translatable and b.translated]
        qe = [b.confidence.translation for b in blocks if b.confidence.translation is not None]
        mean = sum(qe) / len(qe) if qe else 0.0
        mn = min(qe) if qe else 0.0
        low = 100.0 * sum(1 for s in qe if s < cfg.qe_threshold) / len(qe) if qe else 0.0
        print(f"{tag:14}{len(blocks):>7}{len(qe):>7}{mean:>8.3f}{mn:>8.3f}{low:>6.0f}%")
    except Exception as e:
        print(f"{tag:14}  ERROR: {type(e).__name__}: {str(e)[:80]}", file=sys.stderr)
