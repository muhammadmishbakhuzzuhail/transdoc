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
| underline | ✓ | DOCX capture + rendered md/docx/pdf (PR #86); PDF-extract n/a (no font flag, drawn as vector) |
| strikethrough | ✓ | docx capture (run.font.strike) + rendered md/docx/pdf, block+inline #93 |
| highlight / background colour | ✓ | run highlight captured (docx) + rendered md/docx/pdf #97 |
| superscript / subscript | ✓ | inline-runs: captured (docx+pdf) + rendered (md/docx/pdf) #91/#92 |
| small-caps / all-caps | ✓ | docx capture + md/docx/pdf #97/#98 |
| letter-spacing / word-spacing / kerning / baseline-shift | ✗ | rawdict has per-glyph positions |
| hyperlink (URI) | ✓ | captured (PDF get_links + DOCX rels) + rendered (md/docx/pdf) PR #83 |
| character rotation / vertical text | ◐ | detected + skipped in overlay, not preserved |
| per-run language tag | ✓ | output uniformly target language — rebuilt docx default lang set to target (Normal style w:lang) for correct spell-check/hyphenation; source per-run tags moot |
| ligatures | ✓ | folded (PR #75) |

## Paragraph / block level
| Variable | Status | Notes |
|---|---|---|
| alignment (l/c/r/justify) | ✓ | captured + rendered (pdf + docx_out PR #80) |
| line-spacing / space before-after | ✓ | docx capture + docx/pdf render #95 |
| indentation (first-line / left) | ✓ | docx capture + docx/pdf render #95; hanging via list |
| list type / marker / nesting level | ✓ | ordered-vs-bullet + level captured (docx) + rendered (md/docx) PR #87 |
| paragraph border / shading / tab-stops / drop-cap | ✓ | docx para shading + box border + tab-stops (pos/align) + drop-cap frame captured + rendered |
| direction / bidi (RTL) | ◐ | rtl flag + HarfBuzz overlay; PyMuPDF already logical-order on extract |

## Structure
| Variable | Status | Notes |
|---|---|---|
| heading / outline level | ✓ | |
| table of contents / bookmarks | ✓ | captured + titles translated + outline rebuilt in PDF #101 |
| footnote / endnote + reference anchor | ◐ | kept as paragraph, link not preserved |
| caption ↔ figure/table association | ✓ | bbox proximity bind + reading-order snap (pdf/structured); office paths no-op |
| running header / footer (per-section, odd/even, first) | ◐ | pdf: detected + removed (PR #76); docx: header/footer content captured + translated + re-emitted; odd/even/first + per-section variants pending |
| section / column (structural) | ✓ | pdf reading-order (PR #78); docx multi-column count (w:cols) captured + re-emitted |
| page / section breaks | ◐ | reconstruct keeps page geometry; docx manual page breaks captured + reproduced (pageBreakBefore + w:br type=page); section breaks not yet |

## Tables
| Variable | Status | Notes |
|---|---|---|
| merged cells (rowspan/colspan) | ✓ | rendered DOCX (#82 grid+merge) + PDF flow/reconstruct (HTML colspan/rowspan, #88) |
| cell font-size / bold / align / shading | ✓ | captured (docx) + rendered pdf/docx #88/#100; borders ✓; cell padding (tblCellMar) ✓ |
| column widths | ✓ | docx capture + docx widths + pdf colgroup #99; row-heights ✓ (docx + pdf) |
| nested tables | ✓ | docx capture recurse (#nested) + pdf HTML nest + docx cell.add_table; translate recurses cells |

## Page / document
| Variable | Status | Notes |
|---|---|---|
| page size / orientation | ✓ | reconstruct keeps source size |
| margins | ✓ | docx section margins captured + applied #102 |
| page rotation (/Rotate) applied | ✓ | PyMuPDF reports visual coords; reconstruct bakes rotation into an upright page, overlay keeps native /Rotate (verified test_rotation) |
| page-number regeneration | ✗ | removed as furniture, not re-emitted |
| background colour / watermark | ◐ | full-page colour fill captured + repainted in reconstruct (pdf); overlay keeps it natively; watermark (diagonal text/image) still pending |
| document metadata written to output | ✓ | captured + written to PDF + DOCX #94 |

## Non-text
| Variable | Status | Notes |
|---|---|---|
| images (position / size) | ✓ | figure crop + placement |
| vector graphics — lines / rects | ✓ | capture + redraw (PR #71) |
| vector graphics — curves / beziers | ✓ | capture + redraw bezier #96; dashed strokes captured + re-applied |
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
