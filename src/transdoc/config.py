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
    AUTO  : pick per target — editable target -> FLOW; PDF<-PDF -> LAYOUT.
    """

    AUTO = "auto"
    FLOW = "flow"
    LAYOUT = "layout"


class Engine(str, Enum):
    OPENROUTER = "openrouter"  # LLM via OpenRouter (deepseek/qwen/gemma/llama) — default real use
    ANTHROPIC = "anthropic"   # LLM, best quality + glossary/context, needs API key
    NLLB = "nllb"             # offline neural MT, 200 langs — CC-BY-NC (non-commercial!)
    ARGOS = "argos"           # offline Argos/LibreTranslate — MIT/Apache (commercial-safe)
    ECHO = "echo"             # no-op passthrough, for testing the pipeline


class OCREngine(str, Enum):
    TESSERACT = "tesseract"   # system tesseract, always available
    SURYA = "surya"           # GPU, layout + reading order + strong non-Latin
    AUTO = "auto"


class Config(BaseModel):
    source_lang: str = "auto"                 # "auto" or ISO 639 code
    target_lang: str | None = None            # REQUIRED
    domain: str = "auto"
    output_format: OutputFormat = OutputFormat.MARKDOWN
    fidelity: Fidelity = Fidelity.AUTO         # how faithfully output mirrors source
    localize: bool = False                     # convert dates/numbers/units/currency
    register: Register = Register.AUTO
    mode: Mode = Mode.FULL
    pages: str | None = None                   # page selection, e.g. "3-7,10,15-"

    engine: Engine = Engine.ANTHROPIC
    ocr_engine: OCREngine = OCREngine.AUTO

    # Provided glossary: term -> rendering. Extended automatically.
    glossary: dict[str, str] = Field(default_factory=dict)

    # Model knobs
    anthropic_model: str = "claude-opus-4-8"
    nllb_model: str = "facebook/nllb-200-distilled-600M"

    # Confidence threshold below which values are flagged for human review.
    flag_threshold: float = 0.90

    def require_target(self) -> str:
        if not self.target_lang:
            raise ValueError("TARGET_LANG is required. Set config.target_lang.")
        return self.target_lang

    def resolve_fidelity(self, source_is_pdf: bool) -> Fidelity:
        """AUTO -> LAYOUT only for PDF->PDF (visual overlay), else FLOW (editable)."""
        if self.fidelity != Fidelity.AUTO:
            return self.fidelity
        if source_is_pdf and self.output_format in (OutputFormat.PDF, OutputFormat.SAME):
            return Fidelity.LAYOUT
        return Fidelity.FLOW
