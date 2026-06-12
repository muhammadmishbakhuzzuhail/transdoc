"""Pipeline orchestrator. Runs the phases from the agent spec over the IR.

DIAGNOSE -> (RECONSTRUCT) -> TERMINOLOGY -> TRANSLATE -> SELF-REVIEW -> REGENERATE+REPORT,
gated by MODE (full / reconstruct-only / translate-only / diagnose-only).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import Config, Mode
from .diagnose import diagnose
from .extract import extract as extract_ir
from .ingest.detect import detect
from .ir import Document
from .regenerate import regenerate
from .report import build_report


@dataclass
class Result:
    doc: Document
    output_path: str | None
    report_path: str | None
    report_text: str


_ZIP_KINDS = {"docx", "xlsx", "pptx", "epub", "odt"}


def run(input_path: str, cfg: Config, out_path: str | None = None) -> Result:
    # --- Safety guards (reject pathological/malicious input before any heavy work) ---
    from .limits import apply_pil_cap, check_file_size, check_pages, check_zip_bomb
    apply_pil_cap()
    check_file_size(input_path)

    # --- Ingest + detect ---
    det = detect(input_path)

    if det.mime == "application/pdf":
        import fitz
        with fitz.open(input_path) as _d:
            check_pages(_d.page_count)
            # An AcroForm (fillable form) is dense tiny fields — the LAYOUT overlay shrinks
            # the longer translation to an illegible size. Reflow it instead (readable, at the
            # cost of the exact form geometry). Only override when fidelity was left on AUTO.
            from .config import Fidelity as _F
            if (_d.is_form_pdf and cfg.fidelity == _F.AUTO
                    and cfg.resolve_fidelity(True) == _F.LAYOUT):
                cfg.fidelity = _F.FLOW
    elif det.kind.value in _ZIP_KINDS:
        check_zip_bomb(input_path)

    # --- Extract -> IR ---
    doc = extract_ir(det, cfg)

    # --- Phase 1: Diagnose ---
    diagnose(doc, det, cfg)

    if cfg.mode == Mode.DIAGNOSE:
        report = build_report(doc, cfg)
        return Result(doc, None, None, report)

    # --- Phase 2: Reconstruct (OCR repair) — applied inline in extractors today;
    #     dedicated repair pass is a TODO hook here. ---
    if cfg.mode == Mode.RECONSTRUCT:
        # emit the reconstructed source in the requested format, no translation
        outp = _resolve_out(input_path, cfg, out_path)
        # render source text by treating source as output
        for b in doc.blocks:
            b.translated = None  # ensure source text is rendered
        regenerate(doc, cfg, outp)
        report = build_report(doc, cfg)
        return Result(doc, outp, None, report)

    # --- Phases 3-5: Terminology + Translate + Self-review ---
    cfg.require_target()

    # FLOW output reflows the text, so running headers/footers just clutter it (and waste
    # translation calls). Strip them before translating. LAYOUT keeps them in place.
    from .config import Fidelity
    source_is_pdf = (doc.mime == "application/pdf")
    if cfg.resolve_fidelity(source_is_pdf) == Fidelity.FLOW:
        from .extract.base import reorder_vertical_last
        from .headers import strip_running_headers
        strip_running_headers(doc)
        reorder_vertical_last(doc)        # push margin/rotated text to end of its page

    from .translate import get_translator, translate_document

    tr = get_translator(cfg)
    translate_document(doc, tr, cfg)

    # Phase 5b: optional reference-free quality estimation -> flag weak segments
    if cfg.quality_check:
        from .translate.quality import annotate_quality

        annotate_quality(doc, cfg)

    # --- Phase 6: Regenerate + Report ---
    outp = _resolve_out(input_path, cfg, out_path)
    regenerate(doc, cfg, outp)
    report = build_report(doc, cfg)
    report_path = str(Path(outp).with_suffix("")) + ".report.md"
    Path(report_path).write_text(report, encoding="utf-8")
    return Result(doc, outp, report_path, report)


_EXT = {"markdown": ".md", "plain-text": ".txt", "docx": ".docx", "pdf": ".pdf",
        "pptx": ".pptx", "xlsx": ".xlsx", "epub": ".epub", "srt": ".srt", "vtt": ".vtt"}


def _resolve_out(input_path: str, cfg: Config, out_path: str | None) -> str:
    if out_path:
        return out_path
    stem = Path(input_path).with_suffix("")
    fmt = cfg.output_format.value
    if fmt == "same-as-source":
        ext = Path(input_path).suffix or ".md"
    else:
        ext = _EXT.get(fmt, ".md")
    tgt = cfg.target_lang or "out"
    return f"{stem}.{tgt}{ext}"
