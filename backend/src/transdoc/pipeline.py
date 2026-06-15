"""Pipeline orchestrator. Runs the phases from the agent spec over the IR.

DIAGNOSE -> (RECONSTRUCT) -> TERMINOLOGY -> TRANSLATE -> SELF-REVIEW -> REGENERATE+REPORT,
gated by MODE (full / reconstruct-only / translate-only / diagnose-only).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import Config, Fidelity, Mode, OutputFormat
from .diagnose import diagnose
from .extract import extract as extract_ir
from .ingest.detect import detect, is_form_pdf
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
    elif det.kind.value in _ZIP_KINDS:
        check_zip_bomb(input_path)

    # Forms -> PDF: a form is a grid of vector field-lines/boxes. The reconstruct renderer
    # rebuilds a fresh page from text + image crops and would discard that grid (the form
    # collapses into reflowed prose). Route forms to the OVERLAY renderer instead — redact the
    # source text in place and keep the original page (lines, boxes, checkboxes) intact — and
    # to the standard digital extractor, whose bboxes line up with the original text spans the
    # overlay redacts. Only when the user left layout/fidelity on AUTO (explicit choices win).
    if (cfg.fidelity == Fidelity.AUTO and cfg.output_format in (OutputFormat.PDF, OutputFormat.SAME)
            and det.mime == "application/pdf" and is_form_pdf(input_path)):
        cfg.fidelity = Fidelity.LAYOUT          # overlay: keep the form, swap text in place
        if cfg.layout == "auto":
            cfg.layout = "off"                  # standard extract -> bboxes match for redaction

    # --- Extract -> IR ---
    doc = extract_ir(det, cfg)

    # Normalize extracted text: de-hyphenate line breaks, fold ligatures, NFC. PyMuPDF leaves
    # words split across line breaks ("inter-\nnational") and most ligatures intact, which
    # degrade both fidelity and translation. (research 2026-06-15)
    from .extract.textnorm import normalize_doc
    normalize_doc(doc)

    # Drop running headers/footers/page-numbers detected by cross-page repetition in the
    # margins — noise on a reflow + wasted translation calls. (research 2026-06-15)
    from .extract.furniture import drop_repeated
    drop_repeated(doc)

    # --- Phase 1: Diagnose ---
    diagnose(doc, det, cfg)

    if cfg.mode == Mode.DIAGNOSE:
        report = build_report(doc, cfg)
        _cleanup_tmp(doc)
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
        _cleanup_tmp(doc)
        return Result(doc, outp, None, report)

    # --- Phases 3-5: Terminology + Translate + Self-review ---
    cfg.require_target()

    # FLOW output reflows the text, so running headers/footers just clutter it (and waste
    # translation calls). Strip them before translating. LAYOUT keeps them in place.
    source_is_pdf = (doc.mime == "application/pdf")
    if cfg.resolve_fidelity(source_is_pdf) == Fidelity.FLOW:
        from .extract.base import reorder_vertical_last
        from .headers import strip_running_headers
        strip_running_headers(doc)
        reorder_vertical_last(doc)        # push margin/rotated text to end of its page

    from .translate import get_translator, translate_document

    tr = get_translator(cfg)
    translate_document(doc, tr, cfg)

    # Phase 5a: recompute text direction from the TRANSLATED text. An LTR source translated into
    # an RTL target (Arabic/Hebrew/...) must now flow right-to-left, so set Style.rtl from the
    # output before rendering (the renderers already honour style.rtl).
    from .textdir import apply_text_direction

    apply_text_direction(doc, cfg)

    # Phase 5b: optional reference-free quality estimation -> flag weak segments
    if cfg.quality_check:
        from .translate.quality import annotate_quality

        annotate_quality(doc, cfg)

    # --- Phase 6: Regenerate + Report ---
    outp = _resolve_out(input_path, cfg, out_path)
    regenerate(doc, cfg, outp)

    # Phase 6b: optional post-render verification — re-extract the output and diff its structure
    # against the source IR, surfacing content-loss warnings in the report.
    verify_warnings: list[str] = []
    if getattr(cfg, "verify", False):
        from .verify import verify_output
        verify_warnings = verify_output(doc, outp, cfg)

    report = build_report(doc, cfg)
    if verify_warnings:
        report += "\n\n## Post-render verification\n" + "\n".join(
            f"- {w}" for w in verify_warnings)
    report_path = str(Path(outp).with_suffix("")) + ".report.md"
    Path(report_path).write_text(report, encoding="utf-8")
    _cleanup_tmp(doc)
    return Result(doc, outp, report_path, report)


def _cleanup_tmp(doc) -> None:
    """Remove intermediate crop-image temp dirs after rendering (they leaked one per run)."""
    import shutil
    for d in getattr(doc, "tmp_dirs", []):
        shutil.rmtree(d, ignore_errors=True)
    doc.tmp_dirs = []


_EXT = {"markdown": ".md", "plain-text": ".txt", "docx": ".docx", "pdf": ".pdf",
        "pptx": ".pptx", "xlsx": ".xlsx", "epub": ".epub", "srt": ".srt", "vtt": ".vtt",
        "odt": ".odt"}


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
