# transdoc — Document Intelligence & Translation Agent

Translate documents of **any** form to **any** language while **preserving layout**.
Not just translation — it diagnoses, reconstructs (OCR repair), translates, verifies, and
regenerates a clean, faithful document plus a full report.

Combines **DeepL-style translation + iLovePDF-style document tooling +
OCR-to-editable-document**, built on a format-agnostic Intermediate Representation (IR) so any
input maps to any output.

## Scope: personal & local — not commercial

This is a **personal, local-use** project. It is **not distributed or commercialized**, so
**software/model licenses are not a constraint**: AGPL (PyMuPDF), CC-BY-NC weights (NLLB-200,
Surya), and other non-commercial assets are all fair game. The only goals that matter here are
**maximum fidelity and quality**, on a **CPU-only** machine.

Two design rules follow from that:

- **Extraction is the hard part** (the output is rebuilt from scratch), so it is **NOT locked
  to one library** — it fuses the best tool for each sub-task: PyMuPDF for digital text +
  vector graphics + images, an AcroForm parser for form fields, PP-StructureV3 for
  layout/tables/formula-LaTeX/OCR. Best extractor per region, merged into the IR.
- **Translation: one primary engine, chosen by measurement.** A round-trip-chrF benchmark
  (`scripts/bench_engines.py`) settled it: the **Google web endpoint wins** (avg chrF 85.1 vs
  NLLB-200-600M 83.8 across id/ar/zh/de), so the default stays the **`fallback`** chain
  (Google-primary → MyMemory → LibreTranslate backstop for when Google is blocked). NLLB and
  others remain `-e`-selectable; a larger NLLB (1.3B/3.3B) might overtake Google but costs much
  more on CPU.

## Repository layout
```
backend/    Python package (transdoc): pipeline, CLI, FastAPI API, tests, scripts
frontend/   React UI (Vite + TypeScript + Tailwind + shadcn-style)
docs/        design notes (RESEARCH, RISKS)
```
Run the backend from `backend/` (`pip install -e ".[dev,formats]"`, then `transdoc serve`)
and the frontend from `frontend/` (`npm install && npm run dev`). See `backend/README.md`
and `frontend/README.md`.

## Why it's different
- **Form-aware PDF rendering.** PDF→PDF auto-detects **forms** (grids of vector field-lines/
  boxes — IRS W-9/1040) and renders them with the **overlay** path (redact source text in place
  on the original page, keeping every line/box/checkbox), while reflowable documents use
  **reconstruct** (rebuild a fresh page at the source page size, blocks at their original
  positions). `-f flow` forces a clean single-column reflow (best for →DOCX/MD); `-f layout`
  forces overlay.
- **Any input.** Digital PDF, scanned PDF, photos, DOCX, ODT, legacy DOC, images.
- **Any script.** Latin, Arabic (RTL), CJK, Cyrillic, Devanagari, Thai — full Noto coverage.
- **Never invents, never drops.** Uncertain spans are flagged, not silently smoothed over.

## Architecture
```
INGEST → EXTRACT → OCR(if needed) → DIAGNOSE → [IR] → TRANSLATE → REGENERATE → REPORT
                                                 ↑ glossary + TM + confidence
```
The **IR** (`src/transdoc/ir.py`) is the single canonical model. Every extractor writes IR;
every renderer reads IR; translation edits IR in place. Swap any OCR/translation engine or
output format without touching the rest.

## Stack (see `docs/RESEARCH.md` for the verified rationale)
| Layer | Default | Fallback |
|-------|---------|----------|
| OCR + layout | PP-StructureV3 (PaddleOCR) for layout/tables/formula-LaTeX + Tesseract (CPU, 100+ langs) with geometry-preserving cleanup + auto-escalation on low-confidence pages. Install `tesseract-data-<lang>` and pass `--source` for non-English scans. | Surya OCR 2 (CC-BY-NC model — fine for personal use) |
| Language detect | langdetect (core, tiny) | lingua low-accuracy mode (`[detect]` extra — 100% vs 91% acc, deterministic, ~1.2GB RAM) |
| PDF parse | PyMuPDF | — |
| Office parse | python-docx · odfpy · python-pptx · openpyxl · ebooklib · LibreOffice | — |
| Translate (primary) | **`fallback`** — Google web endpoint (best measured quality, chrF 85.1) → MyMemory → LibreTranslate backstop. CPU-only, no model. | offline NMT NLLB/MADLAD/Opus-MT/Argos + LLM (openrouter/anthropic) all `-e`-selectable; NLLB-600M measured ≈ Google (83.8), bigger NLLB heavier on CPU |
| Translation memory | persistent SQLite cache (cross-run, cuts engine calls) | in-memory dedupe |
| Regenerate | **in-place** text swap for Office (docx/pptx/xlsx/epub/srt/vtt) — keeps all formatting, the DeepL strategy · PDF/image reflow (reconstruct) · `-f layout` overlay opt-in | Markdown |

> **Default = `fallback` (Google-primary), chosen by benchmark.** `scripts/bench_engines.py`
> (round-trip chrF) found Google best (85.1) vs offline NLLB-200-600M (83.8) on id/ar/zh/de, so
> Google stays primary with MyMemory + self-hosted LibreTranslate as backstops for when it's
> rate-limited/blocked. A persistent SQLite TM caches every segment so each is sent at most once.
>
> ⚠️ Google's web endpoint is unofficial/network-dependent. For fully **offline/private**
> translation use `-e nllb` (≈Google quality at 600M, larger models heavier) or
> `-e libretranslate` (self-host). A bigger NLLB (1.3B/3.3B) may beat Google but is much slower
> on CPU — re-run the benchmark before committing to it.

## Install
```bash
python3.11 -m venv .venv && . .venv/bin/activate
pip install -e .                 # core (CPU path)
pip install -e ".[surya]"        # GPU OCR
pip install -e ".[nmt]"          # offline NMT (MADLAD/Opus-MT/NLLB)
pip install -e ".[llm]"          # OpenRouter/Anthropic engines
pip install -e ".[formats]"      # subtitles · EPUB · PowerPoint · Excel
pip install -e ".[detect]"       # lingua language detection (more accurate, ~1.2GB RAM)
```

## Usage
```bash
transdoc translate input.pdf  --lang id --to docx           # PDF → translated Word (free Google chain)
transdoc translate deck.pptx  --lang id --to same-as-source # PowerPoint, layout preserved in place
transdoc translate book.epub  --lang id --to same-as-source # EPUB round-trip
transdoc translate subs.srt   --lang id --to same-as-source # subtitles, timing untouched
transdoc translate sign.jpg   --lang id --to pdf            # photo → OCR → translation overlaid on the original image (Lens-style)
transdoc translate scan.png   --lang en --ocr tesseract     # image → OCR → translate
transdoc translate hindi.pdf  --lang id --source hi          # non-English scan: pass --source for the right OCR model
transdoc translate paper.pdf  --lang id --glossary terms.json # enforce {source term: target term} consistently
transdoc translate doc.pdf    --lang ar --to pdf -f layout  # layout-preserving overlay
transdoc translate x.pdf      --lang id -e libretranslate   # privacy/offline (self-host backstop)
transdoc convert  in.pdf      --to docx                     # OCR/convert only, no translation
transdoc diagnose input.pdf                                 # profile only
transdoc serve                                              # web UI + REST API
```

Engines (`-e`): `fallback` (default — google→mymemory→libretranslate) · `google` · `mymemory` ·
`libretranslate` · `madlad` · `opusmt` · `argos` · `nllb` · `openrouter` · `anthropic` · `echo`.

## Status
Core pipeline + IR + extractors (PDF/DOCX/ODT/PPTX/XLSX/EPUB/SRT/VTT/image/text) +
OCR (Tesseract default, auto-escalating to PaddleOCR on low-confidence pages; Surya optional) +
translate (primary `fallback`/Google chain, benchmark-selected; offline NMT/LLM engines
selectable via `-e`; persistent SQLite TM, brand/math/token protection) + regenerate (**in-place** Office:
docx/odt/pptx/xlsx/epub/srt/vtt · **form-aware** PDF: overlay for forms, reconstruct otherwise ·
image overlay) + report. See `docs/ARCHITECTURE.md` for the fidelity strategy and
`docs/RISKS.md` for known limits. Quality is measured by the eval harness
(`python -m transdoc.eval.harness`, structure/fidelity/CER/WER/chrF + baseline regression gate).

**Quality tooling** (verify the *rendered* output, not block counts): `scripts/verify_output.py`
(OCR a generated PDF, flag wrong-language pages), `scripts/compare_features.py` (bold/italic/
colour preservation original vs translated), `scripts/bench_quality.py` (round-trip chrF —
avg **88.2** across 9 languages).

Test corpus under `corpus/` — `corpus/real/` (real downloads) + `corpus/synthetic/` (generated
ground-truth); see `corpus/README.md`.

## Privacy
The default `fallback`/`google` engine sends document text to Google's public endpoint
(off-device) — don't use it for confidential documents. For **fully on-device** translation use
`-e nllb` (offline NMT, ≈Google quality) or a self-hosted `-e libretranslate`; text never leaves
your machine. A persistent SQLite TM caches every segment locally (each sent at most once).

## Limits
Uploads are bounded against malicious/pathological input (env-overridable in `limits.py`):
`TRANSDOC_MAX_FILE_MB` (300), `TRANSDOC_MAX_PAGES` (5000), `TRANSDOC_MAX_IMAGE_MP` (300),
`TRANSDOC_MAX_ZIP_MB` (1000) + a decompression-ratio cap (zip-bomb guard for office/EPUB).

## License
Code is Apache-2.0, but this is a **personal, non-commercial, local-use** project, so bundled
dependencies and model weights are used **without license restriction** — including AGPL
(PyMuPDF) and CC-BY-NC weights (NLLB-200, Surya). If you ever fork this for **commercial**
distribution, those constraints come back: swap PyMuPDF→pypdfium2 (Apache) and
NLLB→MADLAD/Opus-MT (commercial-safe). See `docs/TRANSLATION.md`.
