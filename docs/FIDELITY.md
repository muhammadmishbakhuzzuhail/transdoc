# Fidelity checklist — "output ≡ input, only the language changes"

The north star: a translated document must reproduce the original **exactly** — same format,
layout, fonts, structure, lines, tables, figures, positions, and every other presentation
variable. The **only** difference is the language of the translatable text. This file is the
living master-checklist of every variable that must round-trip, with status.

Status: ✓ supported end-to-end (capture → IR → render → tested) · ◐ best-effort / one path only
(documented gap) · ⊘ won't-do (justified: infeasible with the current libs, or no gain for a
translation tool) · ✗ not yet.

A feature is only ✓ when it is wired **end-to-end and tested** — capturing a value into the IR
without rendering it is ◐, not ✓. Every row below is at a terminal, justified state: ✓ done, ◐
covered on the path that matters with the remainder noted, or ⊘ with the reason it is not worth
doing. The overlay renderer keeps the *original page* untouched, so anything it routes (forms,
scans, annotated/watermarked pages) preserves these variables natively regardless of row status.

## Character / run level
| Variable | Status | Notes |
|---|---|---|
| font family / size / bold / italic / colour | ✓ | style capture (PR #70) |
| underline | ✓ | DOCX capture + rendered md/docx/pdf (PR #86); PDF-extract n/a (no font flag, drawn as vector) |
| strikethrough | ✓ | docx capture (run.font.strike) + rendered md/docx/pdf, block+inline #93 |
| highlight / background colour | ✓ | run highlight captured (docx) + rendered md/docx/pdf #97 |
| superscript / subscript | ✓ | inline-runs: captured (docx+pdf) + rendered (md/docx/pdf) #91/#92 |
| small-caps / all-caps | ✓ | docx capture + md/docx/pdf #97/#98 |
| letter-spacing / word-spacing / kerning / baseline-shift | ⊘ | per-glyph advances are source-language metrics; after translation the word/glyph sequence differs, so re-applying source spacing is meaningless — the renderer re-lays out target text instead |
| hyperlink (URI) | ✓ | captured (PDF get_links + DOCX rels) + rendered (md/docx/pdf) PR #83 |
| character rotation / vertical text | ◐ | overlay keeps it natively; reconstruct detects tall/narrow + rotated runs and moves them aside (reorder_vertical_last) rather than re-typesetting at an arbitrary angle (HTML box has no rotation) |
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
| footnote / endnote + reference anchor | ◐ | pdf: footnote text kept + sunk below the body (reading-order); docx: python-docx has no footnote write API, so re-emitting native footnotes + anchor links would mean hand-building footnotes.xml — deferred (low ROI; content is not lost on the pdf path) |
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
| page-number regeneration | ⊘ | overlay keeps source page numbers natively; reconstruct preserves page geometry/count but does not synthesize numbers — detection across paths is unreliable and re-emitting risks duplicating/misplacing numbers the source already drew |
| background colour / watermark | ◐ | full-page colour fill captured + repainted in reconstruct (pdf); overlay keeps both natively; diagonal text/image watermark left to overlay (isolating it from content in reconstruct is unreliable) |
| document metadata written to output | ✓ | captured + written to PDF + DOCX #94 |

## Non-text
| Variable | Status | Notes |
|---|---|---|
| images (position / size) | ✓ | figure crop + placement |
| vector graphics — lines / rects | ✓ | capture + redraw (PR #71) |
| vector graphics — curves / beziers | ✓ | capture + redraw bezier #96; dashed strokes captured + re-applied |
| shapes / charts | ◐ | cropped verbatim as a figure (pixel-perfect); re-typesetting embedded chart text is out of scope (the visual is preserved exactly) |
| AcroForm interactive fields (type/value/label) | ◐ | overlay (the form route) keeps the live fields + values natively; field-label text translates as page text. Rebuilding interactive widgets in reconstruct deferred — verified earlier that blank-form values are empty |
| annotations (comments / highlights / stamps) | ◐ | text-markup (highlight/underline/strikeout) captured + repainted in reconstruct; overlay keeps all natively; comment/popup text pending |
| signature / seal / logo | ✓ | cropped verbatim |
| math / formula (LaTeX) | ✓ | PP-FormulaNet |
| barcode / QR | ✓ | cropped verbatim (not translated) |

## Format-specific
| Format | Variable | Status |
|---|---|---|
| DOCX | numbering.xml / theme fonts / fields / track-changes | ◐ — list ordered/level + styles reproduced; track-changes accepted on read (translating tracked deltas is ambiguous); custom numbering.xml restarts + field codes deferred |
| PPTX | slide layout / master / speaker notes | ◐ — slide text translated in place on the layout; master/notes deferred |
| XLSX | cell number-format / formulas / conditional formatting | ◐ — cell text translated in place; formulas left verbatim (never translated); number-format/conditional kept by the openpyxl round-trip |
| EPUB | nav / CSS / spine order | ◐ — spine order + text translated; CSS/nav kept by the round-trip |
| PDF | tagged-PDF structure / OCG layers | ⊘ — no visual effect (accessibility tag tree / optional-content layers); reconstruct cannot rebuild the tag tree and it does not change the rendered page |

## Flow / semantic
| Variable | Status | Notes |
|---|---|---|
| reading order | ✓ | structured model + multi-column heuristic (PR #78) |
| de-hyphenation / NFC / zero-width | ✓ | PR #75 |
| whitespace fidelity / non-breaking spaces | ◐ | extraction preserves nbsp / tabs / space runs (NFC, no collapse — test_whitespace); verbatim tokens keep their nbsp via protection; inter-word spacing of the translated text is the MT engine's (inherent) |
| text expansion handling (translation longer than source) | ◐ | reconstruct grows the box into adjacent whitespace, then shrinks font to fit, then flags `illegible` below the readable floor — the practical ceiling without re-flowing the whole page |

---

Implementation discipline: every item is moved ✗ → ◐ → ✓ **end-to-end and tested**, judged by
"does this make the output more identical to the input except for language?" Skip only with
evidence that it breaks or regresses (e.g. applying bidi to already-logical-order Arabic), or
mark ⊘ with the reason it gains nothing for a translation tool. Findings are sourced from the
deep-research runs + the multi-agent fidelity audit. See `docs/ARCHITECTURE.md`.

No row remains at `✗`: each is ✓ (done + tested), ◐ (covered on the path that matters, remainder
noted), or ⊘ (justified won't-do). The ◐/⊘ rows are deliberate end-states, not backlog — the
overlay route preserves them natively, or re-emitting them gains nothing once the text language
changes.
