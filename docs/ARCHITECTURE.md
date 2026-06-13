# transdoc — Architecture

How a document of *any* form becomes a faithful, translated document of *any* other form.
This file is the canonical map of the early phases (ingest → extract → OCR → diagnose) and
the format/fidelity decisions. Code citations are `file:line` against the current tree.

## 1. The one idea: a format-neutral IR pivot

Every input is parsed into a single **Intermediate Representation** (`ir.py`): a `Document`
of typed `Block`s (`TITLE/HEADING/PARAGRAPH/LIST_ITEM/TABLE/FIGURE/FORMULA/CAPTION`), each
with text, `bbox`, `style`, `confidence`, and (for tables) `Table`/`Cell` grids.

```
INGEST → EXTRACT → OCR(if needed) → DIAGNOSE → [IR] → TRANSLATE → REGENERATE → REPORT
```

* Every **extractor writes IR**; every **renderer reads IR**; **translation edits IR in
  place**. Swap any OCR/translation engine or output format without touching the rest.
* This is why there is **no N×M input-to-output matrix**. PDF→DOCX and DOCX→PDF are the same
  path: parse to IR, translate the IR, render the IR to the target. The only format-aware
  decision is *fidelity* (§5).

## 2. Order of operations — translate on the IR, convert at render

**We translate first, then convert format.** Translation runs on the neutral IR
(`pipeline.py:60` → `translate/base.py:translate_document`), strictly *before* regeneration
(`pipeline.py:70`). The renderer is what emits the target format, reading the already-
translated IR. Consequences:

* Translation never depends on input or output format — it sees only IR blocks.
* Cross-format conversion (PDF↔DOCX↔MD↔…) is a *render-time* concern, not a translate-time
  one. We do **not** special-case input×output pairs.
* The same segment is translated once and can be rendered into any number of formats.

## 3. Ingest — detect the real kind, never trust the extension

`ingest/detect.py`. libmagic sniffs the true MIME (`_sniff_mime`), mapped to a logical
`Kind`. Subtitles/EPUB are extension-trusted (they sniff as text/zip). PDFs get a deeper
probe (`_classify_pdf:82`): count pages that carry a usable text layer (>20 non-space
chars):

| Pages with text | Kind | Routing |
|---|---|---|
| 0 / N | `PDF_SCAN` | OCR every page |
| N / N | `PDF_DIGITAL` | parse text layer |
| some | `PDF_MIXED` | parse digital pages, OCR the image-only ones |

Legacy `.doc`/`.rtf`/`.odt` route through headless LibreOffice → `.docx`
(`detect.py:convert_to_docx`).

## 4. Extract + OCR — per-element routing (the heart of "mixed content")

A real PDF page can mix typed text, a scanned image, a table, a figure, and math. The
router (`extract/__init__.py` dispatch → `extract/pdf.py:extract`) decides per page, then
per block. This is the part where **scanned text and typed text are treated differently.**

### Page-level decision (`extract/pdf.py:135`)

1. **Page is in `ocr_pages`** (image-only, chosen in `extract/__init__.py:29`) → rasterize
   at **300 dpi** and OCR the whole page (`_ocr_page:130`). OCR blocks carry pixel bboxes.
2. **Page has a text layer but it is CID-font garbage** — `_looks_garbage` finds >10%
   control chars, i.e. PyMuPDF returned raw glyph ids, not real text (`pdf.py:146`) → OCR
   the page instead. *This is the "looks digital but is really a scan" case.*
3. **Otherwise digital** → extract embedded images as `FIGURE` blocks (`pdf.py:154`, so flow
   output can reinsert them and overlay keeps them), then parse text blocks.

### Block-level classification of digital text (`pdf.py:193`)

| Test | Type | Why |
|---|---|---|
| `_looks_formula` (math operator + few prose words + ≥3 lone variable letters) | `FORMULA` | freeze verbatim — translating `head_i = Attention(...)` scrambles sub/superscripts |
| `_looks_tabular` (≥6 *digit-bearing* tokens, >35% of the row) | `TABLE` | merged numeric rows the parser couldn't cell-split — freeze so the grid survives. The digit-bearing guard stops form dotted-leaders from false-positiving |
| else `_guess_type` by font size vs body size | `TITLE`/`HEADING`/`PARAGRAPH` | larger-than-body = heading; ≥1.6× = title |

### Treatment summary

| Element | Detected by | Bbox space | Translated? |
|---|---|---|---|
| Typed digital text | clean `get_text()` | PDF points | yes |
| Scanned page text | `PDF_SCAN`/`PDF_MIXED` page | 300-dpi pixels | yes (via OCR) |
| Fake text layer (CID glyphs) | `_looks_garbage` | 300-dpi pixels | yes (via OCR) |
| Embedded image | `page.get_images` | PDF points | no (kept as figure) |
| Math / formula | `_looks_formula` | PDF points | no (frozen) |
| Numeric table row | `_looks_tabular` | PDF points | no (frozen) |
| Low-confidence OCR | OCR conf < 0.5 | pixels | no (original left un-overlaid, never covered with garbage) |

Images (`extract/image.py`) are deskewed; the OCR copy and a display copy are split so the
overlay places translations over a clean image (`Document.render_path`).

## 5. Fidelity strategy — three approaches, one per format class

There is no single right way to put a translation (which expands +20–30% and breaks
word-to-word alignment) back into a document. transdoc uses the same strategy split DeepL
does — chosen by what the format can do, not a global toggle:

| Format class | Strategy | How | Fidelity |
|---|---|---|---|
| Office with a layout engine — **docx · odt · pptx · xlsx · epub · srt · vtt** | **in-place** | re-open the source file, swap only the run/cell text, leave structure untouched; the app's own engine reflows the longer text | **perfect** — every style/image/table/section preserved |
| **PDF · image · text/html** (no layout engine) | **reconstruct (FLOW)** | detect structure (title/heading/paragraph/list/table/figure + bold/italic/colour/alignment), rebuild a clean flowing document | readable; structure preserved, exact pixel position **not** (inherent — text reflows) |
| opt-in **`-f layout`** | **overlay** | redact the source text bbox, place the translation at the same bbox (`insert_htmlbox`), keep background/images/lines | pixel-faithful **but** shrinks dense pages to illegibility and loses word-level emphasis — niche |

`config.py:resolve_fidelity` returns **FLOW for AUTO** (the readable default). The LAYOUT
overlay is opt-in (`-f layout`) — it was the wrong default: translation expansion in fixed
boxes mangles forms and tables (see `docs/RISKS.md`). The fundamental trade-off: **exact
position (overlay, breaks) vs readability (reflow, repositions) — you cannot have both when
the text length changes.** DeepL makes the same call (reconstruct PDF, in-place Office).

## 5.1 Text fit & cross-script rendering — the expansion problem

Translation changes length. EN→DE/ES/FR/RU/AR typically **expands +15–30%**; EN→ZH/JA/KO is
**fewer characters but wider glyphs**; Thai/Khmer have **no word spaces** (break by
dictionary). A fixed source bbox cannot hold an arbitrarily longer translation, and the page
size must not change in `LAYOUT` mode.

**How DeepL avoids this:** DeepL edits the *native* structure (OOXML runs) and lets the
Word/PowerPoint layout engine reflow automatically — and reconstructs (not overlays) PDF. It
sidesteps the fixed-box problem by giving up pixel fidelity. transdoc's **default FLOW is the
same bet** (in-place for Office, reconstruct for PDF). The opt-in **`LAYOUT` overlay** is the
one place the fixed-box expansion problem bites, so it carries the explicit fit system below —
but it is niche, not the default (overlay mangled dense forms; see `docs/RISKS.md`).

**The fit ladder (`LAYOUT` mode) — escalate cheapest-first, keep the page size fixed:**

| Step | Strategy | Cost | State |
|---|---|---|---|
| 0 | **Measure** required vs available area with per-script font metrics (HarfBuzz shaping) | free | implicit in `insert_htmlbox` |
| 1 | **Justify + tighten line spacing** so wrapped text fills the box evenly | free | done — `align=justify`, `line-height:1.05` (`pdf_out.py:105`) |
| 2 | **Grow the box** into adjacent vertical whitespace when neighbors don't collide (keeps font size) | cheap | **gap — not built** |
| 3 | **Shrink font** to fit, floor ~0.6× | cheap | done — `insert_htmlbox(scale_low=0)`, flag below `OVERFLOW_FLAG_SCALE` (`pdf_out.py:114`) |
| 4 | **Concise re-translation** — ask the engine for a shorter rendering when overflow is severe | engine call, LLM-only | gap — opt-in tier |
| 5 | **Flag** what still won't fit, with the shrink ratio, for human review | free | done — `text_expansion` flag |

**Cross-script rendering is handled by HarfBuzz inside `insert_htmlbox`:** correct shaping
and automatic Noto font substitution for CJK / Thai / Arabic / Devanagari, plus `direction:
rtl` for RTL targets. The one known break is a single line that **mixes RTL + LTR** runs
(PyMuPDF can misorder it) — detected and flagged as `bidi_mixed` (`pdf_out.py:98`), not
silently shipped. Page geometry is never resized in `LAYOUT`; overflow is absorbed by the
ladder above, never by repagination.

## 5.2 Non-text graphics — signatures, stamps, logos, backgrounds, seals

These are not text blocks, so the IR never carries them as translatable content. Behaviour
depends on mode:

* **`LAYOUT` (PDF→PDF):** the original page *is* the canvas. We only redact the bbox of each
  translatable text block and overlay the translation there (`pdf_out.py:86`). Everything
  else — signatures, stamps, logos, watermarks, page backgrounds, vector seals, rule lines —
  is **preserved automatically**, untouched.
* **image→PDF / Lens overlay:** the source image is the page background (`pdf_out.py:163`);
  only OCR'd text regions are covered with a padded opaque box (`pdf_out.py:174`). The rest
  of the photo (logo, stamp, signature) stays.
* **`FLOW` (PDF→DOCX/MD):** only text + **embedded raster images** (captured as `FIGURE`,
  `pdf_out.py`/`extract/pdf.py:154`) are carried over. **Vector** signatures/seals/lines and
  page backgrounds are *not* reconstructed — this is inherent to reflow.

**Risks / known sharp edges:**
1. **Redaction clipping** — a stamp or signature that *overlaps* a text bbox is partly wiped
   by the opaque white redaction fill. A graphics-overlap check (skip/clip the redaction, or
   use transparency) is not yet built.
2. **Text inside a logo** — OCR may read a brand name in a logo and translate it. Mitigate
   with a do-not-translate glossary / brand list (the glossary path exists; a brand list is
   not wired by default).
3. **Watermark text layer** ("CONFIDENTIAL"/"DRAFT") — if it carries a real text layer it
   gets translated like any other block. May or may not be desired; not specially handled.
4. **Low-confidence OCR regions** (handwriting, signatures, seals) are already left
   un-overlaid via the `_ocr_garbage` skip (`pdf_out.py:75`), so a scanned signature is
   preserved rather than covered with gibberish.

## 6. Translate — what runs, and the protections

Default engine = **`fallback`** chain `google → mymemory → libretranslate` (free, CPU-only,
$0). These are dedicated **NMT** services, **not LLMs**. LLM engines (`anthropic`,
`openrouter`) are an opt-in tier and the only ones that honor register/tone. Detail in
`docs/TRANSLATION.md`; stack rationale in `docs/RESEARCH.md`.

On top of the same free engine (`translate/base.py:translate_document`):
* **Token protection** — URLs/emails/numbers/dates/codes masked as `[PH0]`, survive
  translation verbatim, restored after.
* **Glossary enforcement** — one source term → one target rendering, everywhere.
* **TM dedupe + persistent SQLite cache** — every unique segment hits the engine at most
  once, ever (this is what keeps a free Google-web service under the rate limit).
* **Verbatim block types** — `FORMULA` and cell-less `TABLE` blocks are skipped.

## 7. Known gaps (ranked) — early-phase improvements on the table

1. **OCR inside embedded images.** A *digital* page that embeds a *scanned image containing
   text* extracts the image as a `FIGURE` but never OCRs the text inside it, so that text is
   not translated. Fix: optionally OCR `FIGURE` regions above a size threshold.
2. **Digital tables are not cell-reconstructed.** PyMuPDF `page.find_tables()` is available
   but unused; digital tables are either frozen (numeric) or reflowed as a paragraph. Using
   `find_tables()` would recover real `Table`/`Cell` grids for proper translation + render.
3. **Garbage/OCR routing is whole-page.** Partial-CID pages get OCR'd entirely, discarding
   the precise digital text on the good half. Per-block garbage routing would be finer.
4. **Reading order for complex multi-column layouts** relies on `reflow_order`'s
   (page, parse-order) and can mis-order heavy multi-column pages.

These are additive — none change the IR contract or the phase order above.
