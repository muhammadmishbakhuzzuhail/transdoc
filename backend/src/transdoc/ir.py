# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Intermediate Representation (IR).

The IR is the single canonical document model that sits at the center of the pipeline.
Every *extractor* (PDF, DOCX, ODT, image+OCR, ...) writes IR. Every *renderer* (Markdown,
DOCX, PDF, ...) reads IR. Translation operates on IR in place.

This decoupling is the whole point of the architecture: you can swap any input format,
OCR engine, translation engine, or output format without touching the others, because
they only ever speak IR.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class BlockType(str, Enum):
    """Logical role of a block. Drives reading order, translation, and rendering."""

    TITLE = "title"
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    TABLE = "table"          # children carry rows; see Table model
    CAPTION = "caption"
    FOOTNOTE = "footnote"
    HEADER = "header"        # page header
    FOOTER = "footer"        # page footer
    PAGE_NUMBER = "page_number"
    FORM_FIELD = "form_field"
    CODE = "code"            # never translated
    FORMULA = "formula"      # never translated
    STAMP = "stamp"          # seals/stamps — flagged, not translated
    SIGNATURE = "signature"  # flagged, not translated
    FIGURE = "figure"        # image region; no text
    HANDWRITING = "handwriting"
    ASIDE = "aside"          # marginalia / side note in the outer margin (translated, kept)
    OTHER = "other"


# Block types whose text must be carried over verbatim (never sent to the translator).
NON_TRANSLATABLE = {
    BlockType.CODE,
    BlockType.FORMULA,
    BlockType.PAGE_NUMBER,
    BlockType.STAMP,
    BlockType.SIGNATURE,
    BlockType.FIGURE,
}


class BBox(BaseModel):
    """Bounding box in PDF/image points, origin top-left."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


class Style(BaseModel):
    """Visual style hints, best-effort. Renderers use what they can."""

    font: Optional[str] = None
    size: Optional[float] = None
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strike: bool = False                  # strikethrough
    small_caps: bool = False
    all_caps: bool = False
    highlight: Optional[str] = None       # highlight colour name (yellow/green/...) or hex
    color: Optional[str] = None          # hex, e.g. "#000000"
    align: Optional[str] = None          # left|center|right|justify
    rtl: bool = False                    # right-to-left script
    list_level: int = 0
    list_ordered: bool = False           # numbered list vs bullet
    heading_level: int = 0               # 1..6 for HEADING
    space_before: Optional[float] = None  # paragraph spacing (pt)
    space_after: Optional[float] = None
    line_spacing: Optional[float] = None  # multiple (1.0/1.5/2.0)
    indent_left: Optional[float] = None   # left indent (pt)
    indent_first: Optional[float] = None  # first-line indent (pt)
    superscript: bool = False            # footnote refs / inline exponents
    subscript: bool = False
    link: Optional[str] = None           # hyperlink target URI, if the block is a link
    para_shading: Optional[str] = None   # paragraph background fill (hex) — boxed/callout paras
    para_border: bool = False            # paragraph has a box border (pPr/pBdr)
    tab_stops: list[tuple[float, str]] = Field(default_factory=list)  # (pos_pt, align) tab stops
    drop_cap: bool = False               # leading drop-cap (pPr/framePr dropCap)


class Confidence(BaseModel):
    """Provenance + certainty for a piece of text. Drives flagging in the report."""

    ocr: Optional[float] = None          # 0..1 OCR confidence, if from OCR
    translation: Optional[float] = None  # 0..1 translation confidence
    source: str = "digital"              # digital|ocr|reconstructed|manual


class Cell(BaseModel):
    text: str = ""
    translated: Optional[str] = None
    rowspan: int = 1
    colspan: int = 1
    size: Optional[float] = None         # font size (pt) of the cell text, if known
    bold: bool = False
    align: Optional[str] = None          # left|center|right
    shading: Optional[str] = None        # cell background fill (hex)
    table: Optional["Table"] = None      # a table nested inside this cell
    confidence: Confidence = Field(default_factory=Confidence)

    @property
    def output_text(self) -> str:
        return self.translated if self.translated is not None else self.text


class Table(BaseModel):
    rows: list[list[Cell]] = Field(default_factory=list)
    has_header_row: bool = True
    col_widths: list[float] = Field(default_factory=list)   # column widths (pt), if known
    row_heights: list[float] = Field(default_factory=list)  # row heights (pt), if known
    cell_margin: Optional[float] = None                     # uniform cell padding (pt), if known


Cell.model_rebuild()   # resolve Cell.table -> Table forward reference


class TocEntry(BaseModel):
    """A bookmark / table-of-contents outline entry. Title is translated; level + target page
    are carried so the output keeps a navigable, translated outline."""

    level: int = 1
    title: str = ""
    page: int = 1
    translated: Optional[str] = None

    @property
    def output_text(self) -> str:
        return self.translated if self.translated is not None else self.title


class Run(BaseModel):
    """An inline span of a block with its own character style (a bold word, a superscript
    footnote ref, an inline hyperlink). A block carries runs only when its text is NOT
    uniformly styled; a uniform paragraph keeps runs empty and is handled block-level (no
    behavior change). See Block.runs."""

    text: str = ""
    translated: Optional[str] = None
    style: Style = Field(default_factory=Style)

    @property
    def output_text(self) -> str:
        return self.translated if self.translated is not None else self.text


class Block(BaseModel):
    """A single logical unit of the document."""

    id: str                              # stable id, e.g. "p1-b3"
    type: BlockType = BlockType.PARAGRAPH
    page: int = 0
    reading_order: int = 0               # global order across pages

    text: str = ""                       # source text (after reconstruction)
    translated: Optional[str] = None     # filled by translate phase
    lang: Optional[str] = None           # detected source language (ISO 639)

    bbox: Optional[BBox] = None
    style: Style = Field(default_factory=Style)
    confidence: Confidence = Field(default_factory=Confidence)
    # Inline character runs — populated only when the block's text is NOT uniformly styled
    # (e.g. a bold word or superscript ref inside a paragraph). Empty = uniform, handled by the
    # block-level `style` (no behavior change). When present, output renders run-by-run.
    runs: list[Run] = Field(default_factory=list)

    table: Optional[Table] = None        # only for BlockType.TABLE
    image_path: Optional[str] = None     # only for BlockType.FIGURE — extracted image file
    anchor_id: Optional[str] = None      # CAPTION -> id of the figure/table it describes, so the
                                         # caption stays adjacent to its media in reading order
    page_break_before: bool = False      # an explicit manual page break precedes this block
                                         # (DOCX: w:br type=page or pPr/pageBreakBefore)
    crop_region: bool = False            # layout-detected non-text region: render by cropping
                                         # the source page at bbox (verbatim figure/math/chart)

    # Free-form flags surfaced in the report. e.g. {"unclear": "best-guess?"}
    flags: dict[str, str] = Field(default_factory=dict)

    @property
    def is_translatable(self) -> bool:
        return self.type not in NON_TRANSLATABLE and bool(self.text.strip())

    @property
    def output_text(self) -> str:
        """Text to render: translation if present, else source (verbatim blocks)."""
        return self.translated if self.translated is not None else self.text


class Repair(BaseModel):
    """A single reconstruction edit made in Phase 2."""

    block_id: str
    before: str
    after: str
    reason: str


class GlossaryEntry(BaseModel):
    term: str
    rendering: str                       # chosen target rendering
    action: str = "translate"            # translate|keep|transliterate|keep+gloss
    rationale: Optional[str] = None


class DocProfile(BaseModel):
    """Phase 1 output."""

    input_nature: str = "unknown"        # digital|ocr|scan|photo|mixed
    damage_level: str = "clean"          # clean|minor|heavy
    damage_examples: list[str] = Field(default_factory=list)
    source_langs: list[str] = Field(default_factory=list)
    genre: str = "unknown"
    structure: list[str] = Field(default_factory=list)
    reading_order_kind: str = "single-column"
    risk_flags: list[str] = Field(default_factory=list)


class Document(BaseModel):
    """The full IR document. Carried end-to-end through the pipeline."""

    source_path: Optional[str] = None
    mime: Optional[str] = None
    source_lang: Optional[str] = None
    target_lang: Optional[str] = None
    # For image sources: a deskewed copy whose geometry matches the OCR bboxes, used as the
    # overlay background so the translation lands straight and in-place. None -> use source.
    render_path: Optional[str] = None

    profile: DocProfile = Field(default_factory=DocProfile)
    blocks: list[Block] = Field(default_factory=list)
    glossary: list[GlossaryEntry] = Field(default_factory=list)
    repairs: list[Repair] = Field(default_factory=list)

    page_count: int = 1
    page_sizes: dict[int, tuple[float, float]] = Field(default_factory=dict)
    # Per-page vector line-art (lines/rects in PDF points) captured from the source so the
    # reconstruct renderer can redraw rules/dividers/boxes it would otherwise drop. See
    # extract/vectors.py.
    page_drawings: dict[int, list[dict]] = Field(default_factory=dict)
    # Per-page /Rotate (0/90/180/270). Non-zero pages are flagged for review — placement on a
    # rotated page is harder and worth surfacing.
    page_rotation: dict[int, int] = Field(default_factory=dict)
    # Source document metadata (title/author/language/...) from the PDF info dict or office
    # core properties. `language` seeds source-language detection when the caller left it auto.
    metadata: dict[str, str] = Field(default_factory=dict)
    # Temp directories of intermediate crop images, cleaned by the pipeline after rendering
    # (they were leaking one dir per run under /tmp).
    tmp_dirs: list[str] = Field(default_factory=list)
    # Auto-mined glossary suggestions from this run: (term, rendering, source_kind). Applied this
    # run for consistency but not persisted as applied entries — surfaced in the report for the user
    # to confirm (PR-2). source_kind is 'auto' (mining) or, later, 'fuzzy'.
    glossary_suggestions: list[tuple[str, str, str]] = Field(default_factory=list)
    # Fuzzy-TM suggestions from this run: (source, matched_past_source, matched_past_translation,
    # score). The engine still translated these segments; the close past match is surfaced for the
    # user to review (PR-4). 0.75 <= score < auto-threshold.
    fuzzy_suggestions: list[tuple[str, str, str, float]] = Field(default_factory=list)
    # PDF outline / bookmarks (level, title, target page) — titles translated, outline rebuilt.
    toc: list[TocEntry] = Field(default_factory=list)
    # Page margins (pt): {left,right,top,bottom}. Carried to the rebuilt document.
    page_margins: dict[str, float] = Field(default_factory=dict)
    # Per-page background fill (hex) for coloured (non-white) pages — painted first in
    # reconstruct so the page colour survives. Absent page -> plain white.
    page_background: dict[int, str] = Field(default_factory=dict)
    # Section header / footer paragraphs (DOCX). Kept off `blocks` so they translate but render
    # into the output section's header/footer, not the body. Other renderers ignore them.
    headers: list["Block"] = Field(default_factory=list)
    footers: list["Block"] = Field(default_factory=list)
    # DOCX footnotes / endnotes / comments — separate XML parts python-docx doesn't model, kept
    # apart from `blocks` so the in-place renderer's paragraph index-zip stays 1:1 with the body.
    notes: list["Block"] = Field(default_factory=list)
    # Number of newspaper-style columns in the (first) DOCX section body. 1 = single column.
    section_columns: int = 1
    # Per-page text-markup annotations (highlight/underline/strikeout) — repainted in reconstruct
    # (overlay keeps the source annotations natively). See extract/annots.py.
    page_annots: dict[int, list[dict]] = Field(default_factory=dict)

    def ordered_blocks(self) -> list[Block]:
        return sorted(self.blocks, key=lambda b: (b.page, b.reading_order))

    def translatable_blocks(self) -> list[Block]:
        return [b for b in self.blocks if b.is_translatable]

    def flagged_blocks(self) -> list[Block]:
        return [b for b in self.blocks if b.flags]
