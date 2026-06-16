"""Pipeline orchestrator. Runs the phases from the agent spec over the IR.

DIAGNOSE -> (RECONSTRUCT) -> TERMINOLOGY -> TRANSLATE -> SELF-REVIEW -> REGENERATE+REPORT,
gated by MODE (full / reconstruct-only / translate-only / diagnose-only).
"""

from __future__ import annotations

import contextlib
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config, Fidelity, Mode, OutputFormat
from .diagnose import diagnose
from .extract import extract as extract_ir
from .ingest.detect import detect, is_form_pdf
from .ir import Document
from .regenerate import regenerate
from .report import build_report

log = logging.getLogger("transdoc.pipeline")


@dataclass
class Result:
    doc: Document
    output_path: str | None
    report_path: str | None
    report_text: str
    timings: dict[str, float] = field(default_factory=dict)   # per-stage wall-clock (seconds)


@contextlib.contextmanager
def _stage(timings: dict[str, float], name: str):
    """Time a pipeline stage: record wall-clock into `timings` and emit a structured log line.
    Observability — lets a slow/failing run be attributed to a specific stage without a profiler."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        dt = time.perf_counter() - t0
        timings[name] = timings.get(name, 0.0) + dt
        log.info("stage=%s seconds=%.3f", name, dt)


def _timing_report(timings: dict[str, float]) -> str:
    if not timings:
        return ""
    rows = "\n".join(f"- {k}: {v:.3f}s" for k, v in timings.items())
    return f"\n\n## Timing\n{rows}\n- **total: {sum(timings.values()):.3f}s**"


_ZIP_KINDS = {"docx", "xlsx", "pptx", "epub", "odt"}


def run(input_path: str, cfg: Config, out_path: str | None = None) -> Result:
    # --- Safety guards (reject pathological/malicious input before any heavy work) ---
    from .limits import apply_pil_cap, check_file_size, check_pages, check_zip_bomb
    apply_pil_cap()
    check_file_size(input_path)
    timings: dict[str, float] = {}

    # --- Ingest + detect ---
    with _stage(timings, "detect"):
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
    with _stage(timings, "extract"):
        doc = extract_ir(det, cfg)

    # Normalize extracted text: de-hyphenate line breaks, fold ligatures, NFC. PyMuPDF leaves
    # words split across line breaks ("inter-\nnational") and most ligatures intact, which
    # degrade both fidelity and translation. (research 2026-06-15)
    # Drop running headers/footers/page-numbers detected by cross-page repetition in the
    # margins — noise on a reflow + wasted translation calls. (research 2026-06-15)
    with _stage(timings, "normalize"):
        from .extract.furniture import drop_repeated
        from .extract.textnorm import normalize_doc
        normalize_doc(doc)
        drop_repeated(doc)

    # --- Phase 1: Diagnose ---
    with _stage(timings, "diagnose"):
        diagnose(doc, det, cfg)

    if cfg.mode == Mode.DIAGNOSE:
        report = build_report(doc, cfg) + _timing_report(timings)
        _cleanup_tmp(doc)
        return Result(doc, None, None, report, timings)

    # --- Phase 2: Reconstruct (OCR repair) — applied inline in extractors today;
    #     dedicated repair pass is a TODO hook here. ---
    if cfg.mode == Mode.RECONSTRUCT:
        # emit the reconstructed source in the requested format, no translation
        outp = _resolve_out(input_path, cfg, out_path)
        # render source text by treating source as output
        for b in doc.blocks:
            b.translated = None  # ensure source text is rendered
        with _stage(timings, "regenerate"):
            regenerate(doc, cfg, outp)
        report = build_report(doc, cfg) + _timing_report(timings)
        _cleanup_tmp(doc)
        return Result(doc, outp, None, report, timings)

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
    with _stage(timings, "translate"):
        translate_document(doc, tr, cfg)
        # Phase 5a: recompute text direction from the TRANSLATED text. An LTR source translated
        # into an RTL target (Arabic/Hebrew/...) must now flow right-to-left — set Style.rtl from
        # the output before rendering (the renderers already honour style.rtl).
        from .textdir import apply_text_direction
        apply_text_direction(doc, cfg)

    # Phase 5b: rule-based QA (always-on, deterministic, model-free) -> flag entity/placeholder/
    # untranslated/empty (hard) + length/glossary (soft). Complements the optional COMET QE below.
    from .translate.qa import run_qa
    with _stage(timings, "qa"):
        qa_findings = run_qa(doc, cfg)

    # Phase 5c: optional reference-free quality estimation (COMET-Kiwi) -> flag weak segments.
    # Runs before escalation so a low COMET score can also trigger the gate.
    if cfg.quality_check:
        with _stage(timings, "quality_check"):
            from .translate.quality import annotate_quality
            annotate_quality(doc, cfg)

    # Phase 5d: hybrid QE-gate (opt-in) -> re-translate the weak segments with the local doc-context
    # LLM, then re-run QA so the report reflects the improved output.
    if cfg.escalate:
        with _stage(timings, "escalate"):
            from .translate.escalate import escalate_weak
            if escalate_weak(doc, cfg, qa_findings):
                qa_findings = run_qa(doc, cfg)

    # --- Phase 6: Regenerate + Report ---
    outp = _resolve_out(input_path, cfg, out_path)
    with _stage(timings, "regenerate"):
        regenerate(doc, cfg, outp)

    # Phase 6b: optional post-render verification — re-extract the output and diff its structure
    # against the source IR, surfacing content-loss warnings in the report.
    verify_warnings: list[str] = []
    if getattr(cfg, "verify", False):
        with _stage(timings, "verify"):
            from .verify import verify_output
            verify_warnings = verify_output(doc, outp, cfg)

    report = build_report(doc, cfg)
    if verify_warnings:
        report += "\n\n## Post-render verification\n" + "\n".join(
            f"- {w}" for w in verify_warnings)
    from .translate.qa import qa_report
    report += qa_report(qa_findings)
    report += _glossary_suggestions_report(doc)
    report += _timing_report(timings)
    report_path = str(Path(outp).with_suffix("")) + ".report.md"
    Path(report_path).write_text(report, encoding="utf-8")
    _cleanup_tmp(doc)
    return Result(doc, outp, report_path, report, timings)


def _glossary_suggestions_report(doc) -> str:
    """Surface this run's auto-mined glossary suggestions so the user can confirm them into the
    persistent glossary (PR-2). They were applied this run for consistency but not persisted."""
    sug = getattr(doc, "glossary_suggestions", None)
    if not sug:
        return ""
    src, tgt = doc.source_lang or "?", doc.target_lang or "?"
    rows = "\n".join(f"- `{term}` → `{ren}`" for term, ren, _kind in sug)
    return ("\n\n## Glossary suggestions\n"
            f"Auto-detected recurring terms (applied this run, not yet persisted). Confirm with "
            f"`transdoc glossary add <term> <rendering> -s {src} -t {tgt}`:\n{rows}")


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
