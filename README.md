# transdoc — Document Intelligence & Translation Agent

Translate documents of **any** form to **any** language while **preserving layout**.
Not just translation — it diagnoses, reconstructs (OCR repair), translates, verifies, and
regenerates a clean, faithful document plus a full report.

Open-source alternative combining **DeepL-style translation + iLovePDF-style document
tooling + OCR-to-editable-document**, built on a format-agnostic Intermediate
Representation (IR) so any input maps to any output.

## Why it's different
- **Layout-preserving translation.** Two fidelity modes: `flow` (clean editable output for
  DOCX/MD) and `layout` (visual overlay that keeps the original page geometry — translate a
  PDF and it still looks like the original). Most open-source tools can't do the latter.
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
| OCR + layout | Tesseract (CPU, 100+ langs); auto-OCR fallback when a page's digital text is CID-font garbage; low-confidence OCR is left un-overlaid (never covers the original with garbage). Install `tesseract-data-<lang>` and pass `--source` for non-English scans. | Surya OCR 2 (GPU, non-commercial model) |
| Language detect | langdetect (core, tiny) | lingua low-accuracy mode (`[detect]` extra — 100% vs 91% acc, deterministic, ~1.2GB RAM) |
| PDF parse | PyMuPDF | — |
| Office parse | python-docx · odfpy · python-pptx · openpyxl · ebooklib · LibreOffice | — |
| Translate (free, CPU) | **`fallback`** — Google web endpoint → MyMemory → self-hosted LibreTranslate (no API key, runs CPU-only) | Offline NMT: MADLAD-400/Opus-MT/Argos (commercial-safe) · NLLB (non-commercial) · OpenRouter/Anthropic (API) |
| Translation memory | persistent SQLite cache (cross-run, cuts engine calls) | in-memory dedupe |
| Regenerate | round-trip in place (pptx/xlsx/epub/srt/vtt) · PyMuPDF `insert_htmlbox` overlay · python-docx | Markdown |

> **Free public service (DocTranslator-style):** the default `fallback` engine proxies the
> free Google Translate web endpoint, so the server hosts no model and runs CPU-only. When
> Google rate-limits, it falls through to MyMemory and a self-hosted LibreTranslate backstop.
> The persistent SQLite TM means any segment is sent to Google at most once, ever.
>
> ⚠️ The Google web endpoint is unofficial/ToS-grey and can be blocked at scale — the
> fallback chain + self-hosted LibreTranslate is what keeps the service alive. The
> legally-clean free fallbacks are **MyMemory** (50k chars/day with email) and a
> **self-hosted LibreTranslate** (unlimited; AGPL stays at arm's length — separate process,
> called only over HTTP, never modified). **DeepL Free is deliberately excluded** from the
> public chain: its ToS forbids repackaging/reselling access or building a competing service.
> NLLB-200 is **CC-BY-NC**; for commercial offline use pick MADLAD/Opus-MT/Argos/LibreTranslate.

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
OCR (Tesseract/Surya) + translate (free Google-chain/libretranslate/offline NMT/LLM, persistent
SQLite TM) + regenerate (round-trip pptx/xlsx/epub/srt · md/docx/pdf overlay) + report are in place.
Test corpus under `documents/` (real downloads) and `samples/` (synthetic ground-truth).

## Privacy
The default `fallback`/`google` engine sends document text to Google's public translation
endpoint, and `mymemory` to MyMemory — translation happens **off-device**. Do not use them for
confidential documents. For fully local/offline translation use a **self-hosted LibreTranslate**
(`-e libretranslate`) or an **offline NMT** engine (`-e madlad|opusmt|argos`); these never leave
your machine. A persistent SQLite TM means any segment is sent to an external engine at most once.

## Limits
Uploads are bounded against malicious/pathological input (env-overridable in `limits.py`):
`TRANSDOC_MAX_FILE_MB` (300), `TRANSDOC_MAX_PAGES` (5000), `TRANSDOC_MAX_IMAGE_MP` (300),
`TRANSDOC_MAX_ZIP_MB` (1000) + a decompression-ratio cap (zip-bomb guard for office/EPUB).

## License
Apache-2.0 (code). Bundled model weights carry their own licenses — see above.
