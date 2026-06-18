"""Pipeline configuration. Mirrors the CONFIGURATION block of the agent spec."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Mode(str, Enum):
    FULL = "full-pipeline"
    RECONSTRUCT = "reconstruct-only"
    TRANSLATE = "translate-only"
    DIAGNOSE = "diagnose-only"


class OutputFormat(str, Enum):
    MARKDOWN = "markdown"
    DOCX = "docx"
    PDF = "pdf"
    PLAIN = "plain-text"
    PPTX = "pptx"
    XLSX = "xlsx"
    EPUB = "epub"
    SRT = "srt"
    VTT = "vtt"
    ODT = "odt"
    SAME = "same-as-source"


class Register(str, Enum):
    AUTO = "auto"
    FORMAL = "formal"
    NEUTRAL = "neutral"
    CASUAL = "casual"


class Fidelity(str, Enum):
    """How faithfully the output mirrors the source.

    FLOW  : semantic reconstruction (headings/paragraphs/tables). Editable, clean.
            Best for ->DOCX/MD/ODT. Layout = logical structure, not pixel-exact.
    LAYOUT: visual overlay. Keep original page geometry, redact source text, place the
            translation at the original bbox (PyMuPDF insert_htmlbox). Pixel-faithful.
            Best for PDF->PDF. The differentiator most tools lack.
    AUTO  : FLOW for everything (the readable default). LAYOUT is opt-in via -f layout.
    """

    AUTO = "auto"
    FLOW = "flow"
    LAYOUT = "layout"
    RECONSTRUCT = "reconstruct"   # positioned per-page rebuild: source page size/count +
                                  # original block positions, text reflowed in place (DeepL-like)


class Engine(str, Enum):
    GOOGLE = "google"         # ★default — benchmark winner (chrF 85.1); free web endpoint, CPU-only, ToS-grey
    FALLBACK = "fallback"     # optional resilient chain google->mymemory->libretranslate (backstops)
    MYMEMORY = "mymemory"     # free fallback, ~50k words/day, no key
    LIBRETRANSLATE = "libretranslate"  # self-host backstop + privacy/offline (AGPL, separate service)
    MADLAD = "madlad"         # offline NMT, 450 langs, any->any — Apache-2.0 (COMMERCIAL-SAFE)
    OPUSMT = "opusmt"         # offline Opus-MT/Marian, per-pair — MIT (commercial-safe, CPU-fast)
    ARGOS = "argos"           # offline Argos/LibreTranslate — MIT/Apache (commercial-safe, light)
    NLLB = "nllb"             # offline NMT, 200 langs — CC-BY-NC (NON-COMMERCIAL only)
    INDICTRANS = "indictrans"  # offline NMT, 22 Indic langs (multi-script) — MIT (commercial-safe)
    OPENROUTER = "openrouter"  # LLM via OpenRouter (needs API key)
    ANTHROPIC = "anthropic"   # LLM, needs API key
    OLLAMA = "ollama"         # local LLM (Ollama) — document-level context-aware, offline, zero-cost
    ECHO = "echo"             # no-op passthrough, for testing the pipeline


class OCREngine(str, Enum):
    TESSERACT = "tesseract"   # system tesseract, always available
    SURYA = "surya"           # GPU, layout + reading order + strong non-Latin
    PADDLE = "paddle"         # PaddleOCR PP-OCRv5/v6 (lightweight, CPU/GPU) — strong non-Latin
    EASYOCR = "easyocr"       # EasyOCR 80+ langs (torch, box+conf) — strong multilingual escalation
    AUTO = "auto"


class Config(BaseModel):
    source_lang: str = "auto"                 # "auto" or ISO 639 code
    target_lang: str | None = None            # REQUIRED
    domain: str = "auto"
    output_format: OutputFormat = OutputFormat.MARKDOWN
    fidelity: Fidelity = Fidelity.AUTO         # how faithfully output mirrors source
    localize: bool = False                     # convert dates/numbers/units/currency
    auto_glossary: bool = True                  # pin one rendering for repeated proper nouns
    fuzzy_tm: bool = True                        # reuse near-identical past translations from the TM
    fuzzy_auto_threshold: float = 0.95          # >= this AND near-identical text AND same protected
                                                # tokens -> auto-apply the past translation (skip engine)
    fuzzy_suggest_threshold: float = 0.75       # >= this (below auto) -> surface as a review suggestion;
                                                # the engine still translates the segment
    embed_model: str | None = "paraphrase-multilingual-MiniLM-L12-v2"   # sentence-transformer for
                                                # semantic fuzzy rerank; None or unavailable -> lexical
                                                # similarity only (graceful degradation)
    few_shot: bool = True                        # feedback flywheel: inject the user's most similar
                                                # confirmed corrections as few-shot examples in the
                                                # LLM prompt (LLM path only; NMT can't few-shot)
    few_shot_k: int = 3                          # max few-shot exemplars per LLM chunk
    consistency: bool = True                     # post-translate: force identical source text to one
                                                # translation across the document (confirmed>majority)
                                                # (acronyms/multi-word names) across the document
    register: Register = Register.AUTO
    mode: Mode = Mode.FULL
    pages: str | None = None                   # page selection, e.g. "3-7,10,15-"
    bilingual: bool = False                     # emit source + translation together
    quality_check: bool = False                 # run reference-free QE (COMET), flag weak segments
    align_styles: bool = False                  # word-alignment style transfer: redistribute inline
                                                # run styles (bold/italic/super/link) onto the
                                                # whole-block translation via mBERT word alignment, so
                                                # a styled span tracks the right words after reorder/
                                                # expansion. Falls back to per-run translation when the
                                                # aligner is unavailable or the alignment is too sparse.
    escalate: bool = False                       # hybrid QE-gate: re-translate QA-weak segments
                                                # (entity/untranslated/empty/length + low-COMET) with
                                                # the local doc-context LLM (Ollama). Opt-in (needs
                                                # Ollama); best-effort — keeps the NMT output if the
                                                # LLM call fails. The accuracy lever where it matters.
    repair: bool = False                         # LLM OCR repair pass: conservatively fix obvious
                                                # OCR errors in low-confidence scanned blocks via the
                                                # local LLM (Ollama) BEFORE translation. Opt-in (needs
                                                # Ollama); every edit is logged to doc.repairs. Keeps
                                                # the original text on any failure / uncertain block.
    verify: bool = False                        # re-extract the rendered output and diff its
                                                # structure (block/table/figure counts, text
                                                # length) against the source IR -> report warnings
    review: bool = False                        # emit a <output>.review.tsv sidecar (block_id,
                                                # source, translation, correction) for the human
                                                # feedback loop — fill the correction column and
                                                # `transdoc feedback import` it (PR-3)
    ocr_figures: bool = False                   # OCR text inside large embedded images
                                                # (a scanned image sitting on a digital page)
    layout: str = "auto"                         # "auto" -> PP-StructureV3 structure path when
                                                # paddle is reachable (regions/tables->HTML/
                                                # formula->LaTeX/reading-order = best layout
                                                # fidelity), else heuristic. "paddle" forces it,
                                                # "off" forces the heuristic. Uses in-process
                                                # paddle if installed, else the isolated layout_venv
                                                # subprocess (TRANSDOC_LAYOUT_PYTHON / ./layout_venv).
                                                # "off" = heuristics.
    reading_order_engine: str = "xycut"          # "xycut" = the deterministic recursive-whitespace
                                                # cut (extract/reading_order.py, default, CPU-free).
                                                # "surya" = re-rank blocks by the Surya layout VLM's
                                                # reading position (PDF only, slow, needs surya-ocr).
                                                # Falls back to xycut when Surya is unavailable.

    engine: Engine = Engine.GOOGLE             # benchmark winner (chrF 85.1); personal/local, no fallback chain
    ocr_engine: OCREngine = OCREngine.AUTO

    # Provided glossary: term -> rendering. Extended automatically.
    glossary: dict[str, str] = Field(default_factory=dict)

    # Model knobs
    anthropic_model: str = "claude-opus-4-8"
    nllb_model: str = "facebook/nllb-200-distilled-600M"

    # Ollama (local LLM, document-level context-aware translation). Deterministic (temp=0) so the
    # context-hash TM cache stays valid. Host overridable via config or OLLAMA_HOST env.
    # Model: Gemma-2-9B-it (Ollama `gemma2:9b`) — Google, clean multilingual incl. Indonesian.
    # Chosen after Qwen2.5-7B leaked Chinese on DE->ID (Chinese-origin model drifts to zh at temp=0).
    # Q4 ~5.5 GB on a 6 GB GPU (partial CPU offload). One model, no per-run choice.
    ollama_model: str = "gemma2:9b"
    ollama_host: str = "http://localhost:11434"
    ollama_num_ctx: int = 4096                  # tokens; sized for a 6 GB GPU; batch packs under it
    ollama_timeout: float = 120.0              # per-request seconds
    llm_context_window: int = 2                 # sliding window: N prev (translated) + N next (source)

    # Confidence threshold below which values are flagged for human review.
    flag_threshold: float = 0.90
    # Separate threshold for COMET-Kiwi QE scores. COMET-Kiwi scores cluster lower than OCR
    # confidence (good translations land ~0.6-0.88), so reusing flag_threshold (0.90) would flag
    # almost everything and over-escalate. 0.75 flags only the clearly weak segments.
    qe_threshold: float = 0.75

    def require_target(self) -> str:
        if not self.target_lang:
            raise ValueError("TARGET_LANG is required. Set config.target_lang.")
        return self.target_lang

    def resolve_fidelity(self, source_is_pdf: bool) -> Fidelity:
        """AUTO: a PDF kept as PDF -> RECONSTRUCT (positioned per-page rebuild that preserves
        the source page size, page count, block positions and images — the DeepL approach);
        anything flowing (-> DOCX/MD/TXT) -> FLOW (clean single-column reflow). LAYOUT overlay
        and FLOW are still selectable with ``-f layout`` / ``-f flow``."""
        if self.fidelity != Fidelity.AUTO:
            return self.fidelity
        if source_is_pdf and self.output_format in (OutputFormat.PDF, OutputFormat.SAME):
            return Fidelity.RECONSTRUCT
        return Fidelity.FLOW
