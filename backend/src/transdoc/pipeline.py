# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
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
# OSD script name -> a representative language for that writing system. Used to resolve an
# 'auto' source on a SCAN: OCR can't pick the right model without the language, and the language
# can't be detected without OCR — break the deadlock by detecting the script from the image.
_SCRIPT_TO_LANG = {
    "Devanagari": "hi", "Han": "zh", "Japanese": "ja", "Hangul": "ko", "Bengali": "bn",
    "Tamil": "ta", "Telugu": "te", "Thai": "th", "Cyrillic": "ru", "Arabic": "ar",
    "Hebrew": "he", "Greek": "el",
    # Indic scripts Tesseract has packs for (Paddle/EasyOCR don't): without these, an auto-source
    # scan in them stays 'auto' -> structured PP-StructureV3 on the English model -> garbage.
    "Kannada": "kn", "Malayalam": "ml", "Gujarati": "gu", "Gurmukhi": "pa",
    "Oriya": "or", "Sinhala": "si",
}


def _autosource_script(det) -> str | None:
    """Auto source + a scan/image: OSD-detect the script from the first page and map it to a
    representative language so a non-Latin scan picks the right OCR model (and skips the Latin/
    Chinese-defaulting structured path that turns Devanagari/Arabic into garbage). Latin or
    undetectable -> None (keep 'auto')."""
    from .ingest.detect import Kind
    from .ocr.router import detect_script
    if det.kind not in (Kind.PDF_SCAN, Kind.PDF_MIXED, Kind.IMAGE):
        return None
    try:
        if det.kind == Kind.IMAGE:
            img = Path(det.path).read_bytes()
        else:
            import fitz
            with fitz.open(det.path) as d:
                img = d[0].get_pixmap(dpi=200).tobytes("png")
        return _SCRIPT_TO_LANG.get(detect_script(img) or "")
    except Exception:
        return None


def _script_of(lang: str | None) -> str:
    """Writing system of a language (Latin for anything not in the non-Latin map)."""
    from .ocr.router import LANG_TO_SCRIPT
    return LANG_TO_SCRIPT.get((lang or "").split("-")[0].lower(), "Latin")


def _cross_script_reflow(src: str | None, tgt: str | None) -> bool:
    """True when source and target use DIFFERENT writing systems. The positioned per-block
    reconstruct keeps each block's source geometry, which only stays meaningful within one script
    (text length, direction, and line metrics change across scripts) — across a boundary it leaves
    half-blank pages, flips RTL<->LTR badly, and inflates the page count (Arabic 6->17, Hindi 5->13,
    Thai ->23). Reconstruct therefore stays the default only for same-script work (its sweet spot:
    Latin->Latin like en->id); any script change reflows. False when the source is unknown (auto)."""
    s = (src or "").split("-")[0].lower()
    if not s or s == "auto":
        return False
    return _script_of(s) != _script_of(tgt)


def run(input_path: str, cfg: Config, out_path: str | None = None) -> Result:
    # --- Safety guards (reject pathological/malicious input before any heavy work) ---
    from .limits import apply_pil_cap, check_file_size, check_pages, check_zip_bomb
    apply_pil_cap()
    check_file_size(input_path)
    timings: dict[str, float] = {}

    # --- Ingest + detect ---
    with _stage(timings, "detect"):
        det = detect(input_path)

    # Auto source on a scan/image: resolve the script from the page image (OSD) so non-Latin
    # scans route to the right OCR model instead of a Latin/Chinese default that yields garbage.
    if (cfg.source_lang or "auto").lower() == "auto":
        osd_lang = _autosource_script(det)
        if osd_lang:
            cfg.source_lang = osd_lang
            log.info("auto source: OSD script -> source_lang=%s for OCR routing", osd_lang)

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

    # Optional: re-rank reading order with the Surya layout VLM (PDF only, opt-in, slow). The
    # default XY-cut order is already set by the extractor; this overrides it when requested.
    if cfg.reading_order_engine == "surya":
        with _stage(timings, "reading_order"):
            from .extract.surya_order import surya_reading_order
            surya_reading_order(doc, cfg)

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

    # OCR repair (opt-in): conservatively LLM-correct residual OCR errors in low-confidence scanned
    # blocks, in the source language, before diagnose/translate. Logs every edit to doc.repairs.
    if cfg.repair:
        with _stage(timings, "repair"):
            from .repair import repair_ocr
            repair_ocr(doc, cfg)

    # --- Phase 1: Diagnose ---
    with _stage(timings, "diagnose"):
        diagnose(doc, det, cfg)

    if cfg.mode == Mode.DIAGNOSE:
        report = build_report(doc, cfg) + _timing_report(timings)
        _cleanup_tmp(doc)
        return Result(doc, None, None, report, timings)

    # --- Phase 2: Reconstruct — emit the repaired source in the requested format, no translation.
    #     OCR repair runs above (normalize + the opt-in LLM repair_ocr pass). ---
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

    # AUTO fidelity + a source whose script the positioned per-block rebuild can't preserve
    # (RTL<->LTR direction flip, or CJK->alphabetic, where translated text length/direction change
    # fundamentally) -> reflow instead of reconstruct. The reconstruct keeps source block geometry,
    # which only stays meaningful within one script family; across these boundaries it leaves
    # half-blank pages and inflates the page count (measured: Arabic 6->17, Chinese 7->15 pages vs
    # a clean 7 in flow). Only when the user left fidelity on AUTO and is producing a PDF.
    if (cfg.fidelity == Fidelity.AUTO
            and cfg.output_format in (OutputFormat.PDF, OutputFormat.SAME)
            and doc.mime == "application/pdf"):
        eff_src = cfg.source_lang if (cfg.source_lang and cfg.source_lang != "auto") else doc.source_lang
        if _cross_script_reflow(eff_src, cfg.target_lang):
            cfg.fidelity = Fidelity.FLOW
            log.info("cross-script %s->%s: AUTO -> FLOW (reconstruct can't preserve this layout)",
                     eff_src, cfg.target_lang)

    # FLOW output reflows the text, so running headers/footers just clutter it (and waste
    # translation calls). Strip them before translating. LAYOUT keeps them in place.
    source_is_pdf = (doc.mime == "application/pdf")
    if cfg.resolve_fidelity(source_is_pdf) == Fidelity.FLOW:
        from .extract.base import reorder_vertical_last
        from .extract.crosspage import merge_cross_page, merge_intra_page
        from .headers import strip_running_headers
        strip_running_headers(doc)
        reorder_vertical_last(doc)        # push margin/rotated text to end of its page
        # rejoin a paragraph the extractor split — within a page (mis-segmentation) then across a
        # page break. Flow reflows anyway, so translate it as one unit (better context, no
        # mid-sentence fragment). LAYOUT keeps pages verbatim, so skipped.
        merge_intra_page(doc)
        merge_cross_page(doc)

    from .translate import get_translator, translate_document

    tr = get_translator(cfg)
    with _stage(timings, "translate"):
        translate_document(doc, tr, cfg)
        # Phase 5a0: residual foreign-script cleanup — re-translate non-Latin runs the engine left
        # behind in a Latin-target output (mixed-script source, e.g. inline 中文/العربية in an EN
        # doc). Real engines only; no-op when nothing foreign remains.
        if not getattr(tr, "is_noop", False):
            from .translate.residual import retranslate_foreign_runs
            retranslate_foreign_runs(doc, tr, cfg)
        # Phase 5a: recompute text direction from the TRANSLATED text. An LTR source translated
        # into an RTL target (Arabic/Hebrew/...) must now flow right-to-left — set Style.rtl from
        # the output before rendering (the renderers already honour style.rtl).
        from .textdir import apply_text_direction
        apply_text_direction(doc, cfg)

    # Phase 5a'': word-alignment style transfer — redistribute inline run styles (bold/italic/...)
    # onto the whole-block translation so a styled span tracks the right words after reorder/
    # expansion. Falls back to the per-run translation when the aligner is unavailable/too sparse.
    if cfg.align_styles and not getattr(tr, "is_noop", False):   # skip echo/no-op engines
        with _stage(timings, "align"):
            from .translate.align import restyle_runs
            restyle_runs(doc, cfg)

    # Phase 5a': document-level consistency — force identical source text to one translation
    # (confirmed > majority > first). Before QA so the harmonised output is what gets checked.
    if cfg.consistency:
        with _stage(timings, "consistency"):
            from .translate.consistency import enforce_consistency
            enforce_consistency(doc, cfg)

    # Phase 5b: rule-based QA (always-on, deterministic, model-free) -> flag entity/placeholder/
    # untranslated/empty (hard) + length/glossary (soft). Complements the optional COMET QE below.
    from .translate.qa import run_qa
    with _stage(timings, "qa"):
        qa_findings = run_qa(doc, cfg)

    # Phase 5c: optional reference-free quality estimation (COMET-Kiwi) -> flag weak segments.
    # Runs before escalation so a low COMET score can also trigger the gate.
    if cfg.quality_check:
        with _stage(timings, "quality_check"):
            from .translate.quality import QualityEstimator, annotate_quality
            annotate_quality(doc, cfg)
            # free the QE model's GPU memory before the LLM escalation loads (~5.5GB) — on a 6GB
            # card the two together overflow VRAM ('device memory nearly full').
            if cfg.escalate:
                QualityEstimator.release()

    # Phase 5d: hybrid QE-gate (opt-in) -> re-translate the weak segments with the local doc-context
    # LLM, then re-run QA so the report reflects the improved output.
    if cfg.escalate:
        with _stage(timings, "escalate"):
            from .translate.escalate import escalate_weak
            if escalate_weak(doc, cfg, qa_findings):
                qa_findings = run_qa(doc, cfg)

    # --- Phase 6: Regenerate + Report ---
    # Re-assert caption→media adjacency via the durable anchor_id link: the reorder/merge stages
    # above renumber reading_order and can separate a caption from its figure/table.
    from .extract.base import snap_captions
    snap_captions(doc)
    outp = _resolve_out(input_path, cfg, out_path)
    with _stage(timings, "regenerate"):
        try:
            regenerate(doc, cfg, outp)
        except Exception:
            # A renderer bug must not lose the whole translation: fall back to a Markdown render
            # of the IR so the run always yields a usable file (plus a loud log).
            log.warning("regenerate failed for %s; falling back to a Markdown render",
                        outp, exc_info=True)
            from .regenerate.markdown import render as _md_render
            outp = str(Path(outp).with_suffix(".md"))
            Path(outp).write_text(_md_render(doc, cfg), encoding="utf-8")

    # Phase 6b: optional post-render verification — re-extract the output and diff its structure
    # against the source IR, surfacing content-loss warnings in the report.
    verify_warnings: list[str] = []
    if getattr(cfg, "verify", False):
        with _stage(timings, "verify"):
            from .verify import verify_output
            verify_warnings = verify_output(doc, outp, cfg)

    # Phase 6c: emit the review sidecar for the human feedback loop (opt-in). It carries the source
    # for every translated segment, which a monolingual output cannot, so a re-imported edit can be
    # promoted to a confirmed TM entry keyed by source.
    if getattr(cfg, "review", False):
        from .store.feedback import write_review
        rows = [(b.id, b.text, b.translated) for b in doc.blocks
                if b.is_translatable and b.translated]
        if rows:
            write_review(rows, str(Path(outp).with_suffix("")) + ".review.tsv")

    report = _quality_banner(doc, qa_findings, cfg) + build_report(doc, cfg)
    if verify_warnings:
        report += "\n\n## Post-render verification\n" + "\n".join(
            f"- {w}" for w in verify_warnings)
    from .translate.qa import qa_report
    report += qa_report(qa_findings)
    report += _glossary_suggestions_report(doc)
    report += _fuzzy_suggestions_report(doc)
    report += _timing_report(timings)
    report_path = str(Path(outp).with_suffix("")) + ".report.md"
    Path(report_path).write_text(report, encoding="utf-8")
    _cleanup_tmp(doc)
    return Result(doc, outp, report_path, report, timings)


def _quality_banner(doc, findings, cfg) -> str:
    """A prominent top-of-report warning when a large share of segments carry HARD QA flags
    (untranslated / empty / entity-loss). Previously such flags only appeared deep in the QA
    section, so a low-quality output (e.g. an OCR-garbage scan, or a degenerate MT run) shipped
    with no visible signal. This surfaces the verdict and points at the remedy."""
    # No translatable text at all (empty/blank/undecodable input, OCR found nothing) -> the output
    # will be essentially empty. Surface it loudly instead of shipping a silent blank file.
    if not any(b.is_translatable for b in doc.blocks):
        return ("> ⚠ **No translatable text found** — the input appears to be empty, a blank/"
                "image-only scan with no readable text, or an unsupported/undecodable format. "
                "The output will be (near) empty. Check the source, or pass `--source <lang>` for "
                "a non-Latin scan.\n\n")
    blocks = [b for b in doc.blocks if b.is_translatable and b.translated]
    if not blocks:
        return ""
    hard_ids = {f.block_id for f in findings if f.severity == "hard"}
    ratio = len(hard_ids) / len(blocks)
    if ratio < 0.5:
        return ""
    tip = ("" if getattr(cfg, "escalate", False)
           else " Re-run with `--escalate` (local-LLM repair of weak segments), or check the "
                "source quality (OCR of a poor scan, mis-detected language).")
    return (f"> ⚠ **Low translation quality:** {len(hard_ids)} of {len(blocks)} segments "
            f"({ratio:.0%}) have hard QA flags (untranslated / empty / entity loss)."
            f"{tip}\n\n")


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


def _fuzzy_suggestions_report(doc) -> str:
    """Surface fuzzy-TM matches (75–95%) the engine did NOT auto-apply, so the user can review
    whether the close past translation should have been reused (PR-4)."""
    sug = getattr(doc, "fuzzy_suggestions", None)
    if not sug:
        return ""
    rows = "\n".join(f"- ({int(score * 100)}%) `{src}`\n  - past: `{msrc}` → `{mtgt}`"
                     for src, msrc, mtgt, score in sug)
    return ("\n\n## Fuzzy TM suggestions\n"
            "Similar past translations exist for these segments (engine-translated this run):\n"
            f"{rows}")


def _cleanup_tmp(doc) -> None:
    """Remove intermediate crop-image temp dirs after rendering (they leaked one per run)."""
    import os
    import shutil
    for d in getattr(doc, "tmp_dirs", []):
        shutil.rmtree(d, ignore_errors=True)
    doc.tmp_dirs = []
    # The deskew/orient display PNG (image source overlay background) is a delete=False temp file
    # outside tmp_dirs; clean it too now that rendering is done.
    rp = getattr(doc, "render_path", None)
    if rp and os.path.basename(rp).startswith("transdoc_disp_"):
        try:
            os.unlink(rp)
        except OSError:
            pass


_EXT = {"markdown": ".md", "plain-text": ".txt", "docx": ".docx", "pdf": ".pdf",
        "pptx": ".pptx", "xlsx": ".xlsx", "epub": ".epub", "srt": ".srt", "vtt": ".vtt",
        "odt": ".odt"}


def output_ext(cfg: Config, input_path: str) -> str:
    """Correct output file extension for cfg.output_format (same-as-source -> the source ext).
    Shared so callers that build their own out_path (e.g. the API job runner) don't drift from the
    format map and write, say, real PPTX bytes into a .md file."""
    fmt = cfg.output_format.value
    if fmt == "same-as-source":
        return Path(input_path).suffix or ".md"
    return _EXT.get(fmt, ".md")


def _resolve_out(input_path: str, cfg: Config, out_path: str | None) -> str:
    if out_path:
        return out_path
    stem = Path(input_path).with_suffix("")
    tgt = cfg.target_lang or "out"
    return f"{stem}.{tgt}{output_ext(cfg, input_path)}"
