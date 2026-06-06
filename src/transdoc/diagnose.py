"""Phase 1 — DIAGNOSE. Build a DocProfile from the detected input + extracted IR."""

from __future__ import annotations

from collections import Counter

from .config import Config
from .ingest.detect import Detection, Kind
from .ir import BlockType, Document, DocProfile


def detect_lang(text: str) -> str | None:
    try:
        from langdetect import detect

        return detect(text)
    except Exception:
        return None


def diagnose(doc: Document, det: Detection, cfg: Config) -> DocProfile:
    p = doc.profile

    p.input_nature = {
        Kind.PDF_DIGITAL: "clean digital",
        Kind.PDF_SCAN: "scanned image",
        Kind.PDF_MIXED: "mixed",
        Kind.IMAGE: "photo/scan",
        Kind.DOCX: "clean digital",
        Kind.ODT: "clean digital",
        Kind.TEXT: "clean digital",
    }.get(det.kind, "unknown")

    # damage: from OCR confidence + flags
    ocr_blocks = [b for b in doc.blocks if b.confidence.source == "ocr"]
    low = [b for b in doc.blocks if b.flags]
    if ocr_blocks:
        avg = sum(b.confidence.ocr or 0 for b in ocr_blocks) / len(ocr_blocks)
        p.damage_level = "clean" if avg > 0.9 else "minor noise" if avg > 0.7 else "heavy corruption"
        p.damage_examples = [b.text[:60] for b in low[:2]]
    else:
        p.damage_level = "clean"

    # languages: sample largest blocks
    sample = " ".join(b.text for b in sorted(doc.blocks, key=lambda x: -len(x.text))[:5])
    lang = detect_lang(sample)
    if cfg.source_lang and cfg.source_lang != "auto":
        p.source_langs = [cfg.source_lang]
    elif lang:
        p.source_langs = [lang]
        doc.source_lang = doc.source_lang or lang

    # structural inventory
    counts = Counter(b.type for b in doc.blocks)
    inv = []
    label = {BlockType.TITLE: "title", BlockType.HEADING: "headings",
             BlockType.PARAGRAPH: "paragraphs", BlockType.TABLE: "tables",
             BlockType.LIST_ITEM: "list items", BlockType.FIGURE: "figures",
             BlockType.CAPTION: "captions"}
    for t, c in counts.items():
        inv.append(f"{c} {label.get(t, t.value)}")
    p.structure = inv

    p.genre = cfg.domain if cfg.domain != "auto" else "unknown"

    # reading order kind: rough guess from bbox column spread
    if doc.page_sizes:
        p.reading_order_kind = "multi-column" if _looks_multicolumn(doc) else "single-column"

    if det.kind in (Kind.PDF_SCAN, Kind.IMAGE):
        p.risk_flags.append("OCR output — verify numbers/IDs/names")
    if low:
        p.risk_flags.append(f"{len(low)} low-confidence span(s) flagged")
    return p


def _looks_multicolumn(doc: Document) -> bool:
    page0 = [b for b in doc.blocks if b.page == 0 and b.bbox]
    if len(page0) < 6:
        return False
    w = doc.page_sizes.get(0, (600, 800))[0]
    left = sum(1 for b in page0 if b.bbox.x1 < w * 0.55)
    right = sum(1 for b in page0 if b.bbox.x0 > w * 0.45)
    return left >= 3 and right >= 3
