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
4. **Box-expand fit step is missing** (`ARCHITECTURE.md §5.1` ladder step 2): overflow jumps
   straight to font shrink instead of first growing into adjacent whitespace.
5. **Localization** of numbers/dates/currency (`cfg.localize`) is defined but not implemented
   (1.250,00 ↔ 1,250.00).
6. **Inline math** inside a paragraph isn't protected — only standalone formula lines are.
7. **Multi-column reading order** relies on (page, parse-order) and can mis-order heavy
   multi-column pages.
8. **`find_tables` false positives** — a figure/diagram can be detected as a table in FLOW
   output (guarded to ≥2×2 but not perfect). LAYOUT is unaffected.
9. **Font family** is captured but the overlay renders with Noto substitution, not the
   original face; **underline** isn't reproduced (PyMuPDF exposes no reliable underline flag).
10. **AcroForm widget fields** (interactive form values) may not be extracted/translated.

### 🔒 Security & operations (before public hosting)
11. **Malicious input** — PDF bombs / embedded JS, zip bombs in docx/epub/xlsx. Add size,
    page, and entry-count limits + sandboxing.
12. **LibreOffice subprocess** on untrusted `.doc`/`.rtf` is a large CVE surface — sandbox or
    gate it.
13. **SSRF** via a user-supplied LibreTranslate URL; **path traversal** via output paths.
14. **Privacy disclosure** — the free Google web endpoint sends document text to Google; the
    public service must disclose this and offer the self-hosted LibreTranslate path.
15. **Google endpoint rate-limit / IP-ban at scale** (known). Mitigated by TM cache, batching,
    backoff, and the fallback chain; needs real throughput limits + proxy rotation for prod.

## Translation quality
MT meaning preserved + token protection 100% verbatim across id/ar/zh/ru/ja/fr/hi (spot-checked,
not formally benchmarked). Register/tone (formal/casual) only via the opt-in LLM engines —
the free NMT chain has no tone control.
