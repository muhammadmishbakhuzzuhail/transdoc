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
