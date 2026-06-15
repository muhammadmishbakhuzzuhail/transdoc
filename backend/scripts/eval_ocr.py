"""OCR-accuracy eval with exact, reproducible ground truth.

Most "is the OCR good?" checks have no labels, so they only catch crashes/regressions — not the
error RATE. This measures it: take a born-digital UDHR PDF (whose text layer IS the ground
truth), rasterize it to an image-only PDF (the "scan"), run the pipeline's OCR on that image,
and score the recognized text against the original with CER / WER. No web, no committed
binaries, no manual labels — the gold comes from the same file.

    cd backend && .venv/bin/python -m scripts.eval_ocr                 # all gold-bearing langs
    cd backend && .venv/bin/python -m scripts.eval_ocr english russian # a subset
    cd backend && .venv/bin/python -m scripts.eval_ocr --layout auto   # structured (PP-StructureV3)

Default --layout off measures the Tesseract line-OCR baseline (fast, deterministic). --layout
auto measures the shipped PP-StructureV3 path (needs paddle/GPU).
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Latin + Cyrillic + Greek UDHR PDFs that carry a real text layer (verified). The Indic/CJK/Thai
# "digital" UDHRs are actually image PDFs, so they can't supply gold here.
GOLD_LANGS = ["english", "french", "german", "spanish", "portuguese", "russian", "greek"]
CORPUS = Path("corpus/real/multilingual")


def _norm(s: str) -> str:
    return " ".join((s or "").split())


def gold_text(pdf: Path) -> str:
    import fitz
    d = fitz.open(str(pdf))
    try:
        return _norm("\n".join(p.get_text() for p in d))
    finally:
        d.close()


def rasterize(pdf: Path, out: Path, dpi: int = 150) -> None:
    """Render every page to a raster and rebuild an image-only PDF (no text layer) — a synthetic
    but faithful 'scan' of the source."""
    import fitz
    src = fitz.open(str(pdf))
    dst = fitz.open()
    try:
        for page in src:
            pix = page.get_pixmap(dpi=dpi)
            p = dst.new_page(width=pix.width * 72.0 / dpi, height=pix.height * 72.0 / dpi)
            p.insert_image(p.rect, stream=pix.tobytes("png"))
        dst.save(str(out))
    finally:
        dst.close()
        src.close()


def ocr_text(raster: Path, layout: str) -> str:
    from transdoc.config import Config
    from transdoc.extract import extract
    from transdoc.ingest.detect import detect

    cfg = Config(target_lang="id", layout=layout)
    doc = extract(detect(str(raster)), cfg)
    return _norm(" ".join(b.text for b in doc.ordered_blocks() if b.text.strip()))


def main(argv: list[str]) -> int:
    from transdoc.eval.metrics import cer, wer

    layout = "off"
    if "--layout" in argv:
        i = argv.index("--layout")
        layout = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    show = "--show" in argv
    if show:
        argv = [a for a in argv if a != "--show"]
    langs = argv or GOLD_LANGS

    print(f"OCR eval (layout={layout})  —  CER/WER vs the source text layer\n")
    print(f"{'lang':12} {'chars':>7} {'CER%':>7} {'WER%':>7}")
    print("-" * 36)
    cers, wers = [], []
    with tempfile.TemporaryDirectory(prefix="transdoc_ocreval_") as td:
        for lang in langs:
            pdf = CORPUS / f"udhr_{lang}.pdf"
            if not pdf.exists():
                print(f"{lang:12} {'(missing)':>7}")
                continue
            gold = gold_text(pdf)
            if len(gold) < 50:
                print(f"{lang:12} {'(no text layer)':>7}")
                continue
            raster = Path(td) / f"{lang}.pdf"
            rasterize(pdf, raster)
            got = ocr_text(raster, layout)
            c, w = cer(gold, got) * 100, wer(gold, got) * 100
            cers.append(c)
            wers.append(w)
            print(f"{lang:12} {len(gold):>7} {c:>7.2f} {w:>7.2f}")
            if show:
                print(f"   gold: {gold[:200]}")
                print(f"   ocr : {got[:200]}")
    if cers:
        print("-" * 36)
        print(f"{'mean':12} {'':>7} {sum(cers) / len(cers):>7.2f} {sum(wers) / len(wers):>7.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
