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
- **Translation uses a single engine** — pick the best-quality one and commit to it (default:
  **NLLB-200**, best broad-coverage quality; CC-BY-NC is fine for personal use). No
  license-driven fallback juggling.

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
| Translate (single engine) | **NLLB-200** distilled (offline, CPU via CTranslate2 int8; 200+ langs; best broad-coverage quality; CC-BY-NC — fine for personal use) | other engines stay selectable with `-e` (google/mymemory/libretranslate/madlad/opusmt/argos/nllb/openrouter/anthropic/echo) but NLLB is the committed default |
| Translation memory | persistent SQLite cache (cross-run, cuts engine calls) | in-memory dedupe |
| Regenerate | **in-place** text swap for Office (docx/pptx/xlsx/epub/srt/vtt) — keeps all formatting, the DeepL strategy · PDF/image reflow (reconstruct) · `-f layout` overlay opt-in | Markdown |

> **Personal/offline by default:** the committed engine is **NLLB-200** (offline NMT, CPU via
> CTranslate2 int8) — highest broad-coverage quality and fully on-device, no network, no ToS
> concerns. CC-BY-NC is irrelevant for personal use. A persistent SQLite TM caches every
> segment so repeated runs are instant.
>
> Other engines remain available with `-e` if you want them (e.g. `google` web endpoint for a
> quick no-install pass, `libretranslate` for a self-hosted server), but they are not the
> default and carry their own caveats (network, rate limits). For a personal local tool, one
> strong offline engine beats a license-driven fallback chain.

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
translate (single engine — NLLB-200 default; offline NMT/LLM/network engines selectable;
persistent SQLite TM, brand/math/token protection) + regenerate (**in-place** Office:
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
The default **NLLB-200** engine runs **fully on-device** — document text never leaves your
machine. (If you opt into a network engine like `-e google` or `-e mymemory`, text is sent
off-device to that service; don't use those for confidential documents.) A persistent SQLite
TM caches every translated segment locally.

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
