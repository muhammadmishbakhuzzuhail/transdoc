# Tech Stack Research — Document Intelligence & Translation

Deep-research synthesis (2025–2026 SOTA), adversarially verified: 22 sources → 100 claims
→ 25 verified → 20 confirmed / 5 refuted. Confidence tags below reflect that.

> ⚠️ **Licensing trap (load-bearing):** the highest-quality MT model (NLLB-200) is
> **CC-BY-NC** — *non-commercial, "not for production"*. For a commercial open-source
> release the default engine must be a permissively-licensed one (Argos/LibreTranslate,
> Opus-MT/Marian) or an API (Anthropic). NLLB stays available as an opt-in for
> personal/research use. Translation engine is therefore **pluggable** by design.

## Layer-by-layer verdict

### 1. OCR + Layout  → **Surya OCR 2** (default), **Tesseract** (CPU fallback)
- Surya OCR 2: single **0.65B** VLM → OCR + layout + reading order + table recognition +
  line detection + OCR-error detection across **91 languages**. 87.2% internal pass; 83.3%
  on third-party olmOCR-bench — **best-in-class under 3B params**. Fits 6GB. Engine behind Marker. `[high]`
- Per-language varies: Arabic ~72.7%, Chinese ~82.5%. Arabic-script quality genuinely
  uncertain — **test on own data**. `[caveat]`
- Tesseract: CPU, 100+ langs, no layout, weak on Indic (Devanagari vowel reordering) → fallback only.
- VLM-OCR (GOT-OCR2, Qwen2.5-VL, dots.ocr): higher ceiling but >6GB unless quantized →
  optional/quantized/API. Claim "VLMs beat Surya/Paddle on Arabic by 60% CER" was **refuted**.

### 2. End-to-end conversion (reference architectures to study)
- **Docling** (IBM), **Marker** (uses Surya), **MinerU** — study these; don't reinvent.
- Benchmark: **OmniDocBench** (1651 pages, 10 doc types, 5 layout types incl. handwriting,
  40+ systems). `[high]` — but per-system numeric rankings **did not verify**; re-check leaderboard live. `[caveat]`

### 3. Native parsing  → **PyMuPDF** primary
- PyMuPDF (fitz): text + bbox + font + render + redaction + overlay. Fastest, most complete.
- python-docx (DOCX r/w), odfpy (ODT), **LibreOffice headless** (legacy .doc/.rtf → docx).

### 4. Translation  → pluggable
| Engine | Quality | Langs | License | VRAM | Use |
|--------|---------|-------|---------|------|-----|
| **NLLB-200** | best multilingual, +44% BLEU/40k dirs | 200 | **CC-BY-NC** ✗commercial | int8 ~95MB+ via CTranslate2 | personal/research default |
| **Argos / LibreTranslate** | lower | model-dependent | **MIT/Apache** ✓ | CPU/small | **commercial-safe offline** |
| **Opus-MT / Marian** | good per-pair | per-pair | **MIT** ✓ | small | commercial per-pair |
| **Anthropic LLM** | high, doc-context+glossary | high-resource | API | 0 (cloud) | quality + terminology |
| Local LLM (Qwen/Gemma) | uneven on low-resource | varies | varies | >6GB | high-resource only |
- **CTranslate2 int8** = 2–4× memory cut → fits NLLB on 6GB (int8_float16 GPU / int8 CPU). `[high]`
- LLM fine-tuning does **NOT** beat dedicated NMT on low-resource/distant pairs (refuted). Use
  NMT as workhorse; LLM for document-level context + glossary consistency on supported pairs.

### 5. Regeneration  → **PyMuPDF `insert_htmlbox`** for layout-preserving overlay
- `insert_htmlbox`: HarfBuzz shaping, RTL + complex scripts (Devanagari), auto font sub. `[high]`
- Legacy `insert_textbox`/`fill_textbox`: **no complex-script support** — unusable for Hindi/
  Bengali/Tamil + 120 langs. Avoid. `[high]`
- Weak spot: **mixed RTL+LTR in one line** (Arabic + Latin numerals) still problematic →
  python-bidi + arabic-reshaper + manual run-splitting. `[caveat]`
- ReportLab 4.4.0 (Apr 2025): experimental RTL/Indic shaping — alternative for from-scratch PDF. `[high]`
- DOCX out: python-docx. Fonts: **Noto** (full glyph coverage).

### 6. Reference projects to study
- **HIN_EN_PDF_Translator** — OCRmyPDF/Tesseract + PyMuPDF span extract → redact → overlay
  translated text, transfer font size/color. The buildable layout-preserving pattern. `[high]`
- **OCRmyPDF** — adds OCR text layer back (searchable PDF).
- **LibreTranslate / Argos Translate** — self-hosted MT API, OpenNMT+CTranslate2+SentencePiece.
- **Docling / Marker** — end-to-end conversion.

## Recommended end-to-end stack
```
Ingest:      python-magic + PyMuPDF page-probe (digital vs scan vs mixed)
Preprocess:  OpenCV (deskew/dewarp/denoise, doc-boundary auto-crop)
Extract:     PyMuPDF (PDF) · python-docx (DOCX) · odfpy (ODT) · LibreOffice (legacy)
OCR:         Surya OCR 2 (GPU default) → Tesseract (CPU fallback)
Layout:      Surya layout + reading order (→ IR blocks)
LangDetect:  fasttext / lingua (per block)
Translate:   Anthropic LLM (default, glossary+context)
             → NLLB-200 int8/CTranslate2 (offline, non-commercial)
             → Argos/LibreTranslate (offline, commercial-safe)
Glossary/TM: SQLite + enforcement pass
QA:          COMET / COMETKiwi (optional, gate low-confidence)
Regenerate:  Markdown · DOCX (python-docx) · PDF (PyMuPDF insert_htmlbox overlay,
             Noto fonts, python-bidi+arabic-reshaper for RTL)
Report:      profile + glossary + repairs + flagged items + human-review list
```

## Open questions (verify at build time on the RTX 3050)
1. Measured VRAM/throughput of Surya 2 + NLLB-200 int8 on 6GB — which needs CPU fallback?
2. Docling vs Marker vs MinerU on **non-Latin/RTL** layout (rankings unverified).
3. Best **commercial-safe** quality for non-Latin (Argos/Opus-MT coverage unbenchmarked).
4. Mixed RTL+LTR regeneration reliability.
5. COMET/COMETKiwi VRAM cost on top of OCR+MT.

_Sources: surya (datalab-to/surya), olmOCR-bench, OmniDocBench (opendatalab), NLLB Nature
2024 (s41586-024-07335-x), NLLB HF card, CTranslate2/OpenNMT, LibreTranslate, Argos,
PyMuPDF/Artifex insert_htmlbox, ReportLab 4.4 changelog, HIN_EN_PDF_Translator, OCRmyPDF._

## PaddleOCR-VL evaluation (2026-06) — candidate OCR upgrade tier

Corpus stress test showed Tesseract averages 0.22–0.44 confidence on degraded/non-Latin
scans (manuscripts, CJK/Hebrew/Devanagari) → garbage-skipped → untranslated. PaddleOCR-VL
evaluated as the upgrade tier.

**Verified (web research):**
- **License: Apache-2.0 — commercial-safe.** This is the decisive advantage over Surya
  (non-commercial model) and NLLB (CC-BY-NC). Removes the OCR licensing blocker.
- Architecture: PaddleOCR-VL-0.9B = NaViT dynamic-resolution visual encoder + ERNIE-4.5-0.3B
  LM. 109 languages; SOTA page- and element-level parsing (text/tables/formulas/charts);
  strong on vertical CJK.
- Accuracy (vendor multilingual tests): Arabic 93%+, Chinese 95%+, Japanese 94%+. Devanagari
  NOT benchmarked; "Slavic/minority languages need strengthening".
- CPU inference is supported ("runs on regular CPUs") — but **no published CPU latency
  numbers**. GPU ~0.13 s/page (A100); OpenVINO claims 5.2× CPU speedup, Apple M4 6.1× (tiny).
  Real CPU s/page on our hardware is still UNVERIFIED — the open risk.
- Install: `pip install "paddleocr[doc-parser]"` + **PaddlePaddle** (heavy framework, ~GB;
  separate from torch). Simple API: `PaddleOCRVL().predict(img)` → markdown/json with layout.

## DECISION: use PaddleOCR PP-OCRv6 (lightweight), NOT the 0.9B VL

The heavy `PaddleOCR-VL-0.9B` OOM'd on both CPU (11 GB RAM) and the 6 GB GPU (below). The
**classic lightweight PaddleOCR pipeline (PP-OCRv6 det+rec, ~126 MB total)** fits this
hardware and decisively beats Tesseract. Measured GPU, avg recognition confidence vs the
Tesseract baseline from the corpus sweep:

| scan (lang) | PP-OCR conf | Tesseract conf | s/page | note |
|---|---|---|---|---|
| us_constitution (en) | **0.88** | 0.38 | 4.5 | real English recovered |
| udhr_hindi (hi) | **0.95** | 0.29 | 1.5 | real Devanagari |
| newspaper (german) | **0.98** | 0.67 | 5.3 | 236 lines of Fraktur |
| document_cyrillic (ru) | **0.76** | 0.31 | 0.8 | big lift |
| manuscript_arabic (ar) | 0.49 | 0.43 | 0.7 | degraded source, low ceiling |
| magna_carta (la) | 0.36 | 0.22 | 1.6 | degraded medieval, low ceiling |

Models are tiny (det+rec per language, tens of MB) so this runs **CPU-only** as well — it is a
CPU-compatible upgrade, not a GPU-only tier. API: `PaddleOCR(lang=<iso>).predict(img)` →
`rec_texts` + `rec_scores` + `rec_polys` (boxes), which map cleanly to the Block IR
(text + bbox + confidence). Lang codes are per-language ISO (`en/la/hi/ar/german/ru/el/...`),
NOT script-group names. **Plan: add an opt-in `[paddleocr]` extra + a `PaddleOCREngine`;
Tesseract stays the always-installed default.** The VL model stays a future remote-backend
option only.

### Appendix — why the 0.9B VL was rejected (OOM benchmark)
**EMPIRICAL BENCHMARK (2026-06, dev machine: i5-13450HX, 11 GB RAM, RTX 3050 6 GB):**
- **CPU: not viable — OOM.** The VL rec model loads ~4.7 GB; with the PaddlePaddle runtime it
  pushed the 11 GB-RAM box into zram-swap thrash (10/11 GB RAM + 10/11 GB swap) and was
  OOM-killed before producing output. Needs ≳16 GB RAM.
- **GPU RTX 3050 6 GB: not viable — OOM.** Model occupies 4.7 GB fp32; PaddlePaddle's memory
  pool + first forward pass exceed 6 GB ("available only ~105 MB", needs 144 MB). OOM persists
  after capping input to 1024–1280 px and disabling orientation/unwarp sub-models — the
  **model size (fp32), not input resolution, is the limit.** Needs ≳8 GB VRAM, or an fp16/int8
  build (~2.4 GB, would fit 6 GB).
- **No accuracy numbers** — could not complete a forward pass on this hardware.
- **Escape hatch:** `PaddleOCRVL` exposes `vl_rec_backend` + `vl_rec_server_url` /
  `vl_rec_api_key` → the VL recognizer can run on a **remote GPU server**, matching transdoc's
  proxy economics (offload hard-scan OCR like Google proxies translation), keeping the node
  CPU-only.

**Revised decision:** not runnable locally here. Paths: (a) **Tesseract preprocessing**
(denoise/binarize/upscale), zero-dep CPU near-term win; (b) PaddleOCR-VL as a **remote-backend**
OCR tier (hosted GPU) — architecturally clean; (c) local PaddleOCR-VL only with **fp16/int8**
on ≥8 GB VRAM. The integration plan below applies once one of these unblocks it.

Original gating plan (superseded by the measured result above):
1. Throwaway-venv benchmark on the hardest scans (magna_carta, hindi, hebrew, diamond_sutra):
   measure s/page on CPU + confidence/CER vs Tesseract. (Mind disk: PaddlePaddle is ~GB.)
2. If CPU s/page is acceptable (target < ~10 s/page), add an opt-in `[paddleocr]` extra +
   a `PaddleOCRVLEngine` implementing the `OCREngine` protocol (map VL layout output → Block
   IR with bbox + confidence). Keep Tesseract the default; PaddleOCR-VL as `--ocr paddleocr`.
3. Tesseract preprocessing (denoise/binarize/upscale) remains the zero-dep CPU fallback.

_Sources: PaddlePaddle/PaddleOCR (GitHub), HF PaddlePaddle/PaddleOCR-VL, ERNIE blog
(ernie.baidu.com/blog/posts/paddleocr-vl), PaddleOCR-VL deployment FAQ (issue #16823),
dev.to PaddleOCR-VL-0.9B guide._
