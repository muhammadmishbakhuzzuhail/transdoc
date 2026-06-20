# Configuration

Every knob: the `Config` object (CLI flags and API form fields map onto it), the translation
engines, and the environment variables. For *how to run*, see [USAGE.md](USAGE.md).

> **Scope:** the settings surface. Behaviour of the quality stages those settings switch on is in
> [QUALITY.md](QUALITY.md).

---

## Config fields

All fields live on `Config` (`backend/src/transdoc/config.py`). The **Surface** column shows where
each is reachable: **CLI** flag, **API** form field, **UI** toggle, or **config-only** (set
programmatically / via the API request, no dedicated CLI flag yet).

| Field | Default | Surface | Meaning |
|-------|---------|---------|---------|
| `source_lang` | `auto` | CLI `-s`, API, UI | Source language, or autodetect |
| `target_lang` | *(required)* | CLI `-l`, API, UI | Target language (ISO 639) |
| `output_format` | `markdown` (CLI) / `docx` (API) | CLI `-t`, API, UI | See USAGE for the full list |
| `fidelity` | `auto` | CLI `-f`, API, UI | `auto` / `flow` / `layout` |
| `engine` | `google` | CLI `-e`, API, UI | Translation engine (see below) |
| `ocr_engine` | `auto` | CLI `--ocr`, API, UI | `auto`/`tesseract`/`paddle`/`easyocr`/`surya` |
| `layout` | `auto` (config/API) / `off` (CLI) | CLI `--layout`, API, UI | PP-StructureV3 structured extraction: `auto`/`off`/`paddle` |
| `domain` | `auto` | CLI `-d`, API | Scopes glossary/TM; only LLM engines act on it |
| `register` | `auto` | CLI `-r`, API | `auto`/`formal`/`neutral`/`casual` (LLM engines) |
| `pages` | *(all)* | CLI `-p`, API, UI | Page selection, e.g. `"3-7,10,15-"` |
| `localize` | `false` | CLI, API, UI | Convert dates/numbers/units/currency |
| `bilingual` | `false` | CLI `-b`, API, UI | Emit source + translation together |
| `quality_check` | `false` (CLI) / `true` (API/UI) | CLI `-q`, API `quality`, UI | Reference-free QE (COMET-Kiwi) |
| `align_styles` | `false` (CLI) / `true` (API/UI) | API `align`, UI | Word-alignment style transfer **(no CLI flag yet)** |
| `escalate` | `false` | CLI | QE-gate LLM re-translation of weak segments |
| `verify` | `false` | CLI | Re-extract output, diff structure vs source |
| `review` | `false` | CLI | Emit `<output>.review.tsv` feedback sidecar |
| `repair` | `false` | config-only | LLM OCR repair of low-confidence blocks **(no CLI/API flag yet)** |
| `ocr_figures` | `false` | CLI | OCR text inside large embedded images |
| `auto_glossary` | `true` | config-only | Pin one rendering for repeated proper nouns |
| `fuzzy_tm` | `true` | CLI `--fuzzy` | Reuse near-identical past translations |
| `fuzzy_auto_threshold` | `0.95` | config-only | Auto-reuse cutoff |
| `fuzzy_suggest_threshold` | `0.75` | config-only | Below auto → surface as a review suggestion |
| `consistency` | `true` | CLI `--consistency` | One translation per identical source string |
| `few_shot` | `true` | CLI `--few-shot` | Inject similar confirmed corrections (LLM only) |
| `few_shot_k` | `3` | config-only | Max few-shot exemplars per LLM chunk |
| `reading_order_engine` | `xycut` | config-only | `xycut` (deterministic) or `surya` **(no CLI/API flag yet)** |
| `embed_model` | `paraphrase-multilingual-MiniLM-L12-v2` | config-only | Sentence-transformer for fuzzy/few-shot similarity |
| `glossary` | `{}` | CLI `-g`, API | Per-run term overrides |
| `flag_threshold` | `0.90` | config-only | QA flag cutoff |
| `qe_threshold` | `0.75` | config-only | COMET-Kiwi QE flag/escalate cutoff |
| `anthropic_model` | `claude-opus-4-8` | config-only | Model for the `anthropic` engine |
| `nllb_model` | `facebook/nllb-200-distilled-600M` | config-only¹ | NLLB checkpoint |
| `ollama_model` | `gemma2:9b` | config-only | Local LLM for escalate/repair/context |
| `ollama_host` | `http://localhost:11434` | config-only | Ollama endpoint |
| `ollama_num_ctx` | `4096` | config-only | Context tokens (sized for a 6 GB GPU) |
| `ollama_timeout` | `120.0` | config-only | Per-request seconds |
| `llm_context_window` | `2` | config-only | Sliding doc-context window (N prev + N next) |

> ¹ The `nllb_model` field is currently overridden by the `NLLB_MODEL` env var (see below); set the
> env var to change the checkpoint.

---

## Engines

Select with `--engine/-e` (CLI) or the `engine` form field (API/UI). Default is `google`, chosen by
a round-trip-chrF benchmark (`scripts/bench_engines.py`).

| Engine | Type | Notes / license |
|--------|------|-----------------|
| `google` | online (web endpoint) | **Default.** Best measured quality (chrF 85.1), CPU-only, no model. Unofficial endpoint, ToS-grey. |
| `fallback` | online chain | `google → mymemory → libretranslate` backstops |
| `mymemory` | online | Free, ~50k words/day, no key |
| `libretranslate` | self-host | Privacy/offline backstop (AGPL, separate service) |
| `nllb` | offline NMT | 200 langs, ≈Google quality — **CC-BY-NC (non-commercial)** |
| `madlad` | offline NMT | 450 langs, any→any — Apache-2.0 (commercial-safe) |
| `opusmt` | offline NMT | Per-pair Marian — MIT (commercial-safe, CPU-fast) |
| `argos` | offline NMT | Argos/LibreTranslate models — MIT/Apache (light) |
| `indictrans` | offline NMT | 22 Indic langs, multi-script — MIT |
| `ollama` | local LLM | Document-level context-aware, offline, zero-cost (Gemma via Ollama) |
| `openrouter` | LLM (API key) | Via OpenRouter |
| `anthropic` | LLM (API key) | Claude |
| `echo` | no-op | Passthrough, for testing the pipeline |

This is a personal, local project, so non-commercial weights (NLLB, Surya) are fine. For a
commercial fork, prefer `madlad`/`opusmt`/`argos`. See [TRANSLATION.md](TRANSLATION.md).

---

## Environment variables

| Variable | Affects | Default |
|----------|---------|---------|
| `TRANSDOC_DB_PATH` | Store/TM SQLite path | `$XDG_DATA_HOME/transdoc/transdoc.db` (i.e. `~/.local/share/transdoc/transdoc.db`) |
| `TRANSDOC_TM_PATH` | Legacy TM cache file | `~/.cache/transdoc/tm.sqlite` |
| `TRANSDOC_TM_DISABLE` | Set to bypass the TM cache (verify code fixes that a cache HIT would mask) | unset |
| `TRANSDOC_JOBS_DB` | Async job store path | under the data dir |
| `TRANSDOC_LAYOUT_PYTHON` | Python for the isolated paddle/layout venv | `./layout_venv/bin/python` |
| `TRANSDOC_LAYOUT_DISABLE` | Disable the structured (PP-StructureV3) path | unset |
| `TRANSDOC_DISABLE_LINGUA` | Disable the lingua language detector | unset |
| `TRANSDOC_EASYOCR_GPU` | Allow EasyOCR to use the GPU | unset (CPU) |
| `TRANSDOC_FALLBACK_CHAIN` | Override the `fallback` engine chain | `google,mymemory,libretranslate` |
| `TRANSDOC_BREAKER_FAILS` / `TRANSDOC_BREAKER_COOLDOWN` | Engine circuit-breaker tuning | — |
| `NLLB_MODEL` | NLLB checkpoint | `facebook/nllb-200-distilled-600M` |
| `MADLAD_MODEL` | MADLAD checkpoint | — |
| `QE_MODEL` | COMET-Kiwi model | Unbabel/wmt22-cometkiwi-da |
| `ALIGN_MODEL` | Word-alignment model | bert-base-multilingual-cased |
| `OLLAMA_HOST` | Ollama endpoint | `http://localhost:11434` |
| `OPENROUTER_MODELS` / `OPENROUTER_API_KEY` | OpenRouter engine | — |
| `ANTHROPIC_API_KEY` | Anthropic engine | — |
| `MYMEMORY_EMAIL` | Raise the MyMemory daily quota | — |
| `LIBRETRANSLATE_URL` / `LIBRETRANSLATE_API_KEY` | LibreTranslate endpoint | — |
| `GOOGLE_CONCURRENCY` / `GOOGLE_MIN_INTERVAL` / `GOOGLE_TRANSLATE_MAX_CHARS` | Google web-endpoint rate/size limits | — |
| `XDG_DATA_HOME` / `XDG_CACHE_HOME` | Base dirs for the data/cache paths above | OS default |

Upload limits (in `limits.py`) are also env-overridable: `TRANSDOC_MAX_FILE_MB` (300),
`TRANSDOC_MAX_PAGES` (5000), `TRANSDOC_MAX_IMAGE_MP` (300), `TRANSDOC_MAX_ZIP_MB` (1000).

## Fonts (PDF output, non-Latin scripts)

**PDF output is self-contained.** The PDF renderer shapes text with PyMuPDF (`insert_htmlbox` /
`Story`), which ships its own bundled **Noto** font set (Devanagari, Arabic, CJK, Hebrew, Thai,
Bengali, Tamil, Telugu, Kannada, Malayalam, Gurmukhi, Gujarati, Oriya, Sinhala, Khmer, Lao,
Myanmar, Ethiopic, Georgian, Armenian, …). The glyphs it shapes are **embedded into the generated
PDF**, so non-Latin output renders correctly on any viewer — no host fonts required, and the file
stays portable across machines. Verified on a host with system fonts disabled (`tests/
test_pdf_fonts.py`).

You therefore do **not** need to install system fonts for PDF output. If you want a specific
typeface (e.g. matching a corporate font), installing it system-wide lets HarfBuzz prefer it:

```bash
# Optional — only to prefer a particular face; not required for correct rendering
sudo apt install fonts-noto fonts-noto-cjk      # Debian/Ubuntu
sudo pacman -S noto-fonts noto-fonts-cjk        # Arch
```

Requires `PyMuPDF>=1.26` (the broad bundled-Noto fallback). DOCX/PPTX/XLSX/EPUB outputs embed no
fonts and let the viewer pick one, so they are unaffected either way.

---

See also: [USAGE.md](USAGE.md) · [QUALITY.md](QUALITY.md) · [DEVELOPMENT.md](DEVELOPMENT.md)
