# Fidelity checklist — "output ≡ input, only the language changes"

The north star: a translated document must reproduce the original **exactly** — same format,
layout, fonts, structure, lines, tables, figures, positions, and every other presentation
variable. The **only** difference is the language of the translatable text. This file is the
living master-checklist of every variable that must round-trip, with status.

Status: ✓ supported end-to-end (capture → IR → render → tested) · ◐ partial (captured but not
rendered, or one path only) · ✗ not yet.

A feature is only ✓ when it is wired **end-to-end and tested** — capturing a value into the IR
without rendering it is ◐, not ✓.

## Character / run level
| Variable | Status | Notes |
|---|---|---|
| font family / size / bold / italic / colour | ✓ | style capture (PR #70) |
| underline | ◐ | docx captured; pdf not; render path varies |
| strikethrough | ✗ | drawn as vector near text — needs detection |
| highlight / background colour | ✗ | |
| superscript / subscript | ◐ | IR `Style.superscript` exists, NOT captured/rendered |
| small-caps / all-caps | ✗ | |
| letter-spacing / word-spacing / kerning / baseline-shift | ✗ | rawdict has per-glyph positions |
| hyperlink (URI) / internal anchor | ◐ | IR `Style.link` exists, NOT captured/rendered |
| character rotation / vertical text | ◐ | detected + skipped in overlay, not preserved |
| per-run language tag | ✗ | |
| ligatures | ✓ | folded (PR #75) |

## Paragraph / block level
| Variable | Status | Notes |
|---|---|---|
| alignment (l/c/r/justify) | ✓ | captured + rendered (pdf + docx_out PR #80) |
| line-spacing / space before-after | ✗ | |
| indentation (first-line / left / hanging) | ✗ | |
| list type / marker / nesting level / numbering | ◐ | LIST_ITEM type; marker + level not preserved |
| paragraph border / shading / tab-stops / drop-cap | ✗ | |
| direction / bidi (RTL) | ◐ | rtl flag + HarfBuzz overlay; PyMuPDF already logical-order on extract |

## Structure
| Variable | Status | Notes |
|---|---|---|
| heading / outline level | ✓ | |
| table of contents / bookmarks | ✗ | `doc.get_toc()` available |
| footnote / endnote + reference anchor | ◐ | kept as paragraph, link not preserved |
| caption ↔ figure/table association | ✗ | |
| running header / footer (per-section, odd/even, first) | ◐ | detected + removed (PR #76); not section-aware |
| section / column (structural) | ◐ | reading-order only (PR #78); not structural |
| page / section breaks | ◐ | page geometry kept in reconstruct |

## Tables
| Variable | Status | Notes |
|---|---|---|
| merged cells (rowspan/colspan) | ◐ | captured (#74 dedup, structured HTML spans); NOT rendered as spans |
| cell alignment (h+v) / padding / borders / shading | ✗ | |
| column widths / row heights | ✗ | |
| nested tables | ✗ | |

## Page / document
| Variable | Status | Notes |
|---|---|---|
| page size / orientation | ✓ | reconstruct keeps source size |
| margins | ◐ | |
| page rotation (/Rotate) applied | ◐ | captured (#74), not applied to placement |
| page-number regeneration | ✗ | removed as furniture, not re-emitted |
| background colour / watermark | ✗ | |
| document metadata written to output | ◐ | captured (#74), not written |

## Non-text
| Variable | Status | Notes |
|---|---|---|
| images (position / size) | ✓ | figure crop + placement |
| vector graphics — lines / rects | ✓ | capture + redraw (PR #71) |
| vector graphics — curves / beziers / dashes | ✗ | |
| shapes / charts | ◐ | kept as figure crop |
| AcroForm interactive fields (type/value/label) | ✗ | blank-form value is empty; revisit for filled forms |
| annotations (comments / highlights / stamps) | ✗ | |
| signature / seal / logo | ✓ | cropped verbatim |
| math / formula (LaTeX) | ✓ | PP-FormulaNet |
| barcode / QR | ✓ | cropped verbatim (not translated) |

## Format-specific
| Format | Variable | Status |
|---|---|---|
| DOCX | numbering.xml / theme fonts / fields / track-changes | ✗ |
| PPTX | slide layout / master / speaker notes | ◐ |
| XLSX | cell number-format / formulas / conditional formatting | ◐ |
| EPUB | nav / CSS / spine order | ◐ |
| PDF | tagged-PDF structure / OCG layers | ✗ |

## Flow / semantic
| Variable | Status | Notes |
|---|---|---|
| reading order | ✓ | structured model + multi-column heuristic (PR #78) |
| de-hyphenation / NFC / zero-width | ✓ | PR #75 |
| whitespace fidelity / non-breaking spaces | ◐ | |
| text expansion handling (translation longer than source) | ◐ | grow-box + shrink + flag |

---

Implementation discipline: every item is moved ✗ → ◐ → ✓ **end-to-end and tested**, judged by
"does this make the output more identical to the input except for language?" Skip only with
evidence that it breaks or regresses (e.g. applying bidi to already-logical-order Arabic).
Findings are sourced from the deep-research runs + the multi-agent fidelity audit. See
`docs/ARCHITECTURE.md`.
