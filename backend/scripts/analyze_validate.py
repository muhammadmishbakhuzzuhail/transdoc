"""Quantitative analysis of the validation set: re-run each doc with COMET-Kiwi QE on, then report
per-doc translation-quality stats (mean/min QE, % below the qe_threshold) and rule-based QA flag
counts. Reference-free, so it works without gold translations. GPU is used for COMET when present.

    .venv/bin/python -m scripts.analyze_validate
"""

from __future__ import annotations

from pathlib import Path

from transdoc.config import Config, Engine, OutputFormat
from transdoc.pipeline import run

OUT = Path("out_validate")

CASES = [
    ("arxiv",  "corpus/real/digital_text/arxiv_bert_en.pdf", "en", OutputFormat.PDF),
    ("hindi",  "corpus/real/scanned_pdf/udhr_hindi_scan.pdf", "hi", OutputFormat.PDF),
    ("thai",   "corpus/real/scanned_pdf/udhr_thai_scan.pdf",  "th", OutputFormat.PDF),
    ("zh",     "corpus/real/multilingual/udhr_chinese.pdf",   "zh", OutputFormat.PDF),
    ("arabic", "corpus/real/multilingual/udhr_arabic.pdf",    "ar", OutputFormat.PDF),
    ("w9",     "corpus/real/forms/irs_w9_form.pdf",           "en", OutputFormat.PDF),
    ("docx",   "corpus/synthetic/docx/structured.docx",       "en", OutputFormat.DOCX),
]

_QA_FLAGS = ("entity", "placeholder", "untranslated", "empty", "length", "low_translation_quality")

print(f"{'doc':8} {'blocks':>6} {'QE_n':>5} {'QE_mean':>8} {'QE_min':>7} {'QE<0.75':>8} {'QAflag':>7}")
print("-" * 60)
rows = []
for tag, src, slang, fmt in CASES:
    if not Path(src).exists():
        print(f"{tag:8} (missing)")
        continue
    ext = ".pdf" if fmt == OutputFormat.PDF else ".docx"
    cfg = Config(source_lang=slang, target_lang="id", engine=Engine.GOOGLE,
                 output_format=fmt, quality_check=True)
    try:
        r = run(src, cfg, out_path=str(OUT / f"{tag}_id{ext}"))
    except Exception as e:
        print(f"{tag:8} ERR {type(e).__name__}: {e}")
        continue
    blocks = [b for b in r.doc.blocks if getattr(b, "translated", None)]
    qe = [b.confidence.translation for b in blocks if b.confidence.translation is not None]
    qa = sum(1 for b in blocks if any(f in b.flags for f in _QA_FLAGS))
    mean = sum(qe) / len(qe) if qe else 0.0
    low = sum(1 for s in qe if s < cfg.qe_threshold)
    print(f"{tag:8} {len(blocks):>6} {len(qe):>5} {mean:>8.3f} "
          f"{(min(qe) if qe else 0):>7.3f} {low:>8} {qa:>7}")
    rows.append((tag, mean, len(qe), low))

if rows:
    allmean = sum(m for _, m, _, _ in rows) / len(rows)
    print("-" * 60)
    print(f"{'MEAN':8} {'':>6} {'':>5} {allmean:>8.3f}")
print("DONE")
