# transdoc — v1 readiness & known gaps

Status of the pipeline against real-document edge cases, and what is deliberately deferred.
Companion to `docs/ARCHITECTURE.md`. Updated as gaps are closed.

## Fixed (v1)

| Area | Was broken | Fix |
|---|---|---|
| Forms | IRS dotted-leader rows frozen as numeric tables, never translated | digit-bearing token guard in `_looks_tabular` |
| EPUB | `<?xml?>`/`<!DOCTYPE>` leaked as text | exclude special `NavigableString` subclasses |
| ODT | `<text:list>` items dropped | emit `LIST_ITEM` per list paragraph |
| XLSX→md/docx/pdf | grid flattened to one cell per line | Table IR for cross-format, per-cell for round-trip |
| PDF overlay | white redaction punched holes in background logos | text-only redaction, keep images + line art |
| PDF overlay | bold/italic/colour lost | capture + reproduce dominant-span styling |
| Extraction | line-broken words ("inter-\nnational") translated as two tokens | dehyphenation |
| Glossary | "cat" fired inside "category" | word-boundary match for ASCII terms |
| Page routing | caption over a full-page scan trusted as digital text | image-dominance check → OCR |
| Tables (FLOW) | digital tables reflowed to paragraphs, grid lost | `find_tables` → real Cell grid for cross-format |
| Source lang | bad OCR-detected code crashed all engines | auto-detect fallback in google engine |
| OCR-in-figure | text inside an embedded scan on a digital page never read | `--ocr-figures`: OCR large embedded images, map bboxes to page |
| Running headers | header/footer repeated on every page cluttered FLOW output | FLOW-gated pass strips blocks repeating in the top/bottom band |

94 tests, ruff clean, GitHub Actions CI (py3.11 + 3.12).

## Open gaps — ranked for v1.x

### 🔴 Correctness (next)
1. **Sentence split across blocks.** A sentence broken across two layout blocks is translated
   independently, losing MT context. Fix: merge adjacent same-style blocks before translate
   in FLOW (LAYOUT must stay per-bbox). Low impact today — PyMuPDF blocks are already
   paragraph-level; mostly bites multi-column/page wraps.

### 🟠 Quality / fidelity
1. **Multi-column reading order** relies on (page, parse-order) and can mis-order heavy
   multi-column pages.
2. **`find_tables` false positives** — a figure/diagram can be detected as a table in FLOW
   output (guarded to ≥2×2 but not perfect). LAYOUT is unaffected.
3. **Font family** is captured but the overlay renders with Noto substitution, not the
   original face; **underline** isn't reproduced (PyMuPDF exposes no reliable underline flag).
4. **AcroForm widget fields** (interactive form values) may not be extracted/translated.
5. **Localize** covers only number separators — not date order, units, or currency symbols.

Closed: box-expand fit (`--`overflow grows into whitespace before shrinking), inline-math
protection (LaTeX + sub/superscript vars), locale number formatting (`cfg.localize`).

### 🔒 Security & operations (before public hosting)
1. **Google endpoint rate-limit / IP-ban at scale** (known). Mitigated by TM cache, batching,
   backoff, and the fallback chain; needs real throughput limits + proxy rotation for prod.
2. **LibreOffice memory** — the subprocess is sandboxed (isolated profile + CPU/output-size
   rlimits + wall timeout), but real-memory is not capped (RLIMIT_AS aborts LO); cap it with a
   cgroup/container in production.

Closed: resource limits (file size / page count / image megapixels / zip decompression) in
`limits.py`, enforced in `pipeline.run` + the API (HTTP 413), Pillow pixel cap, and a privacy
disclosure in the README. SSRF is low-risk (the LibreTranslate URL is operator-env, not a
request field); API uses temp files + internal paths only (no caller-supplied output path).
**LibreOffice conversion is sandboxed** — throwaway UserInstallation profile (no shared
state/macro config), CPU + output-size rlimits on the child, `--norestore`/`--nolockcheck`,
and profile cleanup; a malicious legacy doc can't hang or fill the disk.

## Translation quality
**Formally benchmarked** (round-trip back-translation EN→lang→EN, chrF, fallback chain;
`scripts/bench_quality.py`): average chrF **88.2** across 9 languages, all in a tight 85–91
band — id 91, es 91, hi 90, de 89, zh 89, ru 87, fr 86, ar 86, ja 85. Consistent across
Latin / RTL / CJK / Devanagari / Cyrillic; back-translations are faithful paraphrases. Token
protection stays 100% verbatim. Register/tone (formal/casual) only via the opt-in LLM engines
— the free NMT chain has no tone control.

Minor finding (resolved): stray zero-width spaces appear in some back-translations but
**forward output is clean** (ZWSP=0 verified for en→id/de/ar) — a Google-endpoint artifact on
certain reverse pairs only, not in user-facing output.

## Layout overlay legibility (fixed)
Visual review of generated PDFs (not just block counts!) showed dense layouts render badly:
on the IRS-1040 form the expanded Indonesian text shrank to an illegible, overlapping mess
while block counts still said "64/64 translated". Two fixes:
- **Legibility floor + honest report.** The overlay no longer silently ships text shrunk below
  ~6 pt — it flags the block `illegible`, and the report's "Rendering quality" section counts
  them and suggests `--fidelity flow` / `--to docx`.
- **AcroForm PDFs auto-reflow.** A fillable form (PyMuPDF `is_form_pdf`) with AUTO fidelity now
  uses FLOW instead of the overlay — readable reflowed text instead of a mangled grid.
- **Dense-page fallback.** Even a non-AcroForm page is re-rendered as FLOW when the overlay
  left >40% of its blocks illegible (a form-like layout the AcroForm check missed). A few stray
  illegible blocks (e.g. the arabic article at 15%) keep the faithful overlay.
- **Process lesson:** never report "translated OK" from progress/block counts — render and
  look at the output.

## Formatting-feature fidelity (overlay) — honest limits
Feature comparison (`scripts/compare_features.py`, original vs translated span styles):
- **Fixed: bold/italic were over-applied.** Capturing "any span is bold" made the whole
  reflowed block bold — BERT page 1 went from 18 bold spans (source) to 136 (overlay). Now
  bold/italic are taken from the **character majority** of the block (heading stays bold; a
  paragraph with one bold word does not). Bold dropped to ~4 (the genuine dominant-bold runs).
- **Inherent limit: word-level emphasis can't survive.** The overlay inserts ONE styled box
  per reflowed block, and translation breaks word-to-word alignment, so a single bold/italic/
  coloured *word* inside a paragraph is lost — only block-dominant styling (size, dominant
  colour/bold/italic) carries. Source colour 55 spans → 1 (the rest were inline links/marks).
  This is a real limitation of layout-overlay translation, not a bug; `compare_features.py`
  surfaces it instead of hiding it. (Font *family* is likewise approximated via Noto.)

## v2 backlog — empirical, from a corpus stress test
Sweep of `documents/` (70 runs: 19 digital/office × 3 targets + 13 scanned/image → PDF).
**Stability: 0 crashes, 0 zero-block on digital/office.** Quality findings, ranked:

**Fixed (v2):**
- **Silent source-passthrough on throttle** — a throttled Google endpoint returned None and
  the engine kept the *source* text, leaving whole pages untranslated in long PDFs. Now
  retried then raised to the fallback chain; substantial identical-to-source segments are
  flagged `untranslated`.
- **Brand/proper-noun translation** — "Google Brain" → "Google Otak" fixed with a
  case-sensitive built-in brand list (user-extensible via glossary).
- **`find_tables` cost** — skipped on pages with no vector graphics; diagram false positives
  dropped by the filled-cell guard.
- **Heading detection** — numbered sections ("3.2 Attention") and short bold lines
  ("Abstract") are now headings; author bylines stay paragraphs (~30 clean headings recovered
  on arxiv_attention).
- **Vertical sidebar text** (arXiv ID) demoted to CAPTION so it can't become a "# heading",
  and (FLOW) moved to the end of its page in reading order so it no longer interrupts reflow.
- **OCR quality on degraded / non-Latin scans** — added the PaddleOCR (PP-OCRv5/v6) engine
  (`--ocr paddle`, `[paddleocr]` extra). Benchmarked far above Tesseract (Devanagari 0.95 vs
  0.29, Fraktur 0.98 vs 0.67, Cyrillic 0.76 vs 0.31), CPU-capable, Apache-2.0. Verified
  end-to-end on the Hindi scan (clean Devanagari; low-conf flags 135→16). The 0.9B PaddleOCR-VL
  was rejected (OOM on 6 GB GPU / 11 GB RAM). See `docs/RESEARCH.md`.

- **AUTO OCR escalation** — `--ocr auto` (default) now runs Tesseract first and re-OCRs only
  the low-confidence pages (<0.60 avg) with PaddleOCR when installed, keeping the better
  result. Fast on clean pages, strong on degraded/non-Latin scans.

- **PaddleOCR scan-language auto-detect** — when `--source` is "auto", the script is read off
  the image via Tesseract OSD (confidence-gated) and mapped to a PaddleOCR model (Devanagari→hi,
  Arabic→ar, Han→ch, …). Verified: Hindi→hi, Arabic→ar; low-confidence/Latin fall back to the
  English Latin model. Within Latin, per-language refinement (fr/german) is still a TODO.

**Open:**
1. **Within-Latin OCR language refinement** — when OSD reports Latin we use the `en` model; a
   fr/de/es scan could use its specific PaddleOCR model. Marginal (same Latin recognizer), low
   priority.
2. **TM cache key isn't versioned by extractor behaviour** — low impact (changed text just
   misses the cache, never serves stale).
3. **Multi-column reading order — VERIFIED OK.** PyMuPDF parse order is column-aware: on a true
   2-column ACL page (BERT) the left column reads fully top-to-bottom before the right
   (sequence `LLLLRRR`, one column flip). No custom sorter needed.
