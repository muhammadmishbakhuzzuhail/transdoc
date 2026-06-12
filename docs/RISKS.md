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
1. **LibreOffice subprocess** on untrusted `.doc`/`.rtf` is a large CVE surface — has a 120 s
   timeout but is not sandboxed (run it in a jail/container for public use).
2. **Google endpoint rate-limit / IP-ban at scale** (known). Mitigated by TM cache, batching,
   backoff, and the fallback chain; needs real throughput limits + proxy rotation for prod.

Closed: resource limits (file size / page count / image megapixels / zip decompression) in
`limits.py`, enforced in `pipeline.run` + the API (HTTP 413), Pillow pixel cap, and a privacy
disclosure in the README. SSRF is low-risk (the LibreTranslate URL is operator-env, not a
request field); API uses temp files + internal paths only (no caller-supplied output path).

## Translation quality
MT meaning preserved + token protection 100% verbatim across id/ar/zh/ru/ja/fr/hi (spot-checked,
not formally benchmarked). Register/tone (formal/casual) only via the opt-in LLM engines —
the free NMT chain has no tone control.

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
- **Vertical sidebar text** (arXiv ID) demoted to CAPTION so it can't become a "# heading".
- **OCR quality on degraded / non-Latin scans** — added the PaddleOCR (PP-OCRv5/v6) engine
  (`--ocr paddle`, `[paddleocr]` extra). Benchmarked far above Tesseract (Devanagari 0.95 vs
  0.29, Fraktur 0.98 vs 0.67, Cyrillic 0.76 vs 0.31), CPU-capable, Apache-2.0. Verified
  end-to-end on the Hindi scan (clean Devanagari; low-conf flags 135→16). The 0.9B PaddleOCR-VL
  was rejected (OOM on 6 GB GPU / 11 GB RAM). See `docs/RESEARCH.md`.

- **AUTO OCR escalation** — `--ocr auto` (default) now runs Tesseract first and re-OCRs only
  the low-confidence pages (<0.60 avg) with PaddleOCR when installed, keeping the better
  result. Fast on clean pages, strong on degraded/non-Latin scans.

**Open:**
1. **PaddleOCR still needs `--source <iso>`** for the right language model on escalated pages
   (auto language detection of the scan script is not yet wired).
2. **Vertical sidebar text reading order** — now demoted (not a heading) but still placed late
   in FLOW reading order.
3. **TM cache key isn't versioned by extractor behaviour** — low impact (changed text just
   misses the cache, never serves stale).
4. **Multi-column reading order** looked sane on the 2-column arxiv sample, unverified on
   dense/mixed layouts; keep on watch.
