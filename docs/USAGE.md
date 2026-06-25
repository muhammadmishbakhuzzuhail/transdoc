# Usage

How to run transdoc through the **web UI**, the **CLI**, and the **REST API**, with examples for
every input type. For configuration knobs and environment variables see
[CONFIGURATION.md](CONFIGURATION.md); for the quality pipeline see [QUALITY.md](QUALITY.md).

> **Scope of this document:** running the tool. It does *not* cover internals, testing, or the
> eval harness — those live in [DEVELOPMENT.md](DEVELOPMENT.md).

---

## 1. Web UI

The web UI is the primary, beginner-friendly surface: upload → translate → preview before/after →
download.

```bash
cd backend
source .venv/bin/activate          # see README "Quickstart" for first-time setup
python server.py                   # → http://127.0.0.1:8000   (== transdoc serve)
```

- App: <http://127.0.0.1:8000>
- Interactive API docs (Swagger): <http://127.0.0.1:8000/docs>
- Rebind: `python server.py 0.0.0.0 8080` (or `TRANSDOC_HOST` / `TRANSDOC_PORT`).

The frontend dev server (hot-reload UI) runs separately and proxies to the backend:

```bash
cd frontend && npm install && npm run dev   # → http://localhost:5173
```

UI toggles map directly onto config fields: **Quality flags** → `quality_check`,
**Style alignment** → `align_styles`, **Bilingual** → `bilingual`, **Localize** → `localize`.
Both *Quality flags* and *Style alignment* default **on** in the UI.

After a job completes, the per-segment **review** panel lets you edit, accept TM/fuzzy matches,
and (with the optional `[suggest]` extra) pull in-context synonyms, rephrase a segment, or switch
suggestion mode — see [§4.1](#41-review-suggestions-synonyms-rephrase-modes).

---

## 2. CLI

The entry point is the `transdoc` command (installed into the venv). All commands:

| Command | Purpose |
|---------|---------|
| `translate` | Full pipeline: extract → diagnose → translate → regenerate + report |
| `convert` | Reconstruct / convert format only (OCR repair, **no** translation) |
| `ocr` | Make a scanned PDF searchable (invisible OCR text layer, no translation) |
| `serve` | Launch the web UI + REST API |
| `diagnose` | Print a document profile only (Phase 1, no output file) |
| `correct` | Record a human correction (segment → TM, `--term` → glossary) |
| `glossary` | Manage the persistent glossary (add/list/rm/export/import/suggestions/accept) |
| `feedback` | Import human corrections from an edited output or a filled review sidecar |
| `tm` | Inspect / maintain the translation memory |

### 2.1 `translate`

```
transdoc translate INPUT --lang TARGET [options]
```

`--lang/-l` (target ISO 639) is the only required option. Key options:

| Option | Default | Meaning |
|--------|---------|---------|
| `--lang`, `-l` | *(required)* | Target language (ISO 639), e.g. `id`, `ar`, `zh` |
| `--source`, `-s` | `auto` | Source language; pass it for non-English **scans** (selects the OCR model) |
| `--to`, `-t` | `markdown` | Output format — see table below; `same-as-source` keeps the input format |
| `--engine`, `-e` | `google` | Translation engine — see [CONFIGURATION.md](CONFIGURATION.md#engines) |
| `--ocr` | `auto` | OCR engine: `auto`/`tesseract`/`paddle`/`easyocr`/`surya` |
| `--fidelity`, `-f` | `auto` | `auto`/`flow`/`layout` — how faithfully output mirrors source layout |
| `--domain`, `-d` | `auto` | Domain hint (scopes glossary/TM; only LLM engines act on it) |
| `--register`, `-r` | `auto` | `auto`/`formal`/`neutral`/`casual` (LLM engines only) |
| `--pages`, `-p` | *(all)* | Page selection, e.g. `"3-7,10,15-"` |
| `--localize` | off | Convert dates / numbers / units / currency to target conventions |
| `--bilingual`, `-b` | off | Emit source + translation together |
| `--quality`, `-q` | off | Reference-free QE (COMET-Kiwi): score + flag weak segments |
| `--escalate` | off | QE-gate: re-translate QA-weak segments with the local doc-context LLM (Ollama) |
| `--verify` | off | Re-extract the rendered output and diff its structure against the source |
| `--review` | off | Emit `<output>.review.tsv` for the feedback loop |
| `--glossary`, `-g` | — | JSON file of `{source term: target term}` to enforce |
| `--ocr-figures` | off | OCR text inside large embedded images (scan-in-page) |
| `--layout` | `off` | PP-StructureV3 structured extraction: `auto`/`off`/`paddle` |
| `--fuzzy / --no-fuzzy` | on | Reuse near-identical past translations from the TM |
| `--few-shot / --no-few-shot` | on | Inject your most similar confirmed corrections as LLM few-shot examples |
| `--consistency / --no-consistency` | on | Force identical source text to one translation across the document |
| `--out`, `-o` | *(auto)* | Output path |

**Output formats** (`--to`): `markdown`, `docx`, `pdf`, `plain-text`, `pptx`, `xlsx`, `epub`,
`srt`, `vtt`, `odt`, and `same-as-source` (round-trip the input format in place).

#### Examples by input type

```bash
# Digital PDF → translated Word
transdoc translate report.pdf   --lang id --to docx

# Round-trip Office formats in place (layout/formatting preserved)
transdoc translate deck.pptx    --lang id --to same-as-source
transdoc translate book.epub    --lang id --to same-as-source
transdoc translate subs.srt     --lang id --to same-as-source   # timing untouched

# Scanned / non-English PDF — pass --source so the right OCR model loads
transdoc translate hindi.pdf    --lang id --source hi

# Photo / image → OCR → translation overlaid on the original (Lens-style)
transdoc translate sign.jpg     --lang id --to pdf
transdoc translate scan.png     --lang en --ocr tesseract

# Layout-preserving overlay (forms, certificates)
transdoc translate form.pdf     --lang ar --to pdf -f layout

# Quality pass: flag weak segments, then LLM-re-translate them
transdoc translate paper.pdf    --lang id -q --escalate

# Enforce terminology
transdoc translate paper.pdf    --lang id --glossary terms.json

# Privacy / offline (no text leaves the machine)
transdoc translate secret.pdf   --lang id -e nllb
```

### 2.2 `convert` — reconstruct only (no translation)

```bash
transdoc convert scan.pdf --to docx          # OCR-repair a scan into editable Word
transdoc convert in.pdf   --to docx -f flow  # clean single-column reflow
```

Options: `--to` (default `docx`), `--ocr`, `--fidelity`, `--out`.

### 2.3 `ocr` — make a scan searchable

```bash
transdoc ocr scan.pdf --source hi            # add an invisible OCR text layer, no translation
```

Options: `--source` (OCR model language), `--ocr`, `--out`.

### 2.4 `diagnose` — profile only

```bash
transdoc diagnose input.pdf                  # prints the document profile, writes nothing
```

---

## 3. Terminology & feedback (glossary / TM / corrections)

transdoc learns from corrections and reuses them on every later document. See
[QUALITY.md](QUALITY.md#feedback-flywheel) for how the flywheel feeds back into translation.

```bash
# Glossary (term → target rendering, scoped per language pair + domain)
transdoc glossary add "API" "API" --source en --target id          # pin a literal rendering
transdoc glossary list   --source en --target id
transdoc glossary export --source en --target id -o terms.csv      # DeepL-style CSV/TSV/JSON
transdoc glossary import terms.csv                                  # upsert
transdoc glossary suggestions                                      # pending auto-mined terms
transdoc glossary accept  <id>                                     # promote a suggestion

# Record a one-off correction (reused via the TM)
transdoc correct "source segment" "fixed translation" -s en -t id
transdoc correct "API" "API" -s en -t id --term --lock            # lock a glossary term

# Import a filled review sidecar (after `translate --review`)
transdoc feedback import <output>.review.tsv
```

---

## 4. REST API

`POST /api/translate` (multipart form) and `POST /api/batch` accept these fields:
`target_lang` (required), `source_lang`, `output_format`, `engine`, `fidelity`, `domain`,
`register`, `layout`, `ocr_engine`, `bilingual`, `quality` (default **true**), `localize`,
`align` (default **true**), `pages`.

| Endpoint | Purpose |
|----------|---------|
| `GET  /api/health` | Engine/model availability + defaults |
| `POST /api/translate` | Single-file job → returns a job id |
| `POST /api/batch` | Multi-file job → returns a batch id |
| `GET  /api/jobs/{jid}` | Job status / progress |
| `GET  /api/batch/{bid}` | Batch status |
| `GET  /api/download/{jid}` | Download the translated file |
| `GET  /api/report/{jid}` | Translation report |
| `GET  /api/analysis/{jid}` | Per-segment analysis (QE, flags) |
| `GET  /api/preview/{jid}/{which}/{page}.png` | Rendered before/after page previews |
| `POST /api/correct` | Persist a per-segment correction (feeds the TM flywheel) |
| `POST /api/alternatives` | N alternative translations for a segment (accepts `style`) |
| `POST /api/synonyms` | In-context synonyms for a selected phrase (review assist) |
| `POST /api/rephrase` | Rewrite a segment in a chosen style/mode (review assist) |

```bash
curl -F file=@report.pdf -F target_lang=id -F output_format=docx \
     http://127.0.0.1:8000/api/translate
```

> The web API intentionally exposes a conservative subset of CLI options. Power features
> (`--escalate`, `--verify`, `--repair`, per-request glossary) are CLI-only by design; use the CLI
> for those.

### 4.1 Review suggestions (synonyms, rephrase, modes)

The review surface offers optional, LLM-backed edit assists on the translated text (a
Grammarly/DeepL-Write-style layer, **not** a full editor): select a phrase → in-context
**synonyms**; **rephrase** a segment; a **suggestion mode** (`general`, `professional`,
`academic`, `friendly`, `concise`) that steers rephrase + alternatives. Picks apply locally to
that segment.

These run on a small local instruct LLM (Qwen2.5-3B-Instruct, 4-bit on a 6 GB GPU) behind the
optional extra:

```bash
pip install -e ".[suggest]"        # transformers + torch + accelerate + bitsandbytes
```

Without it (or without a GPU) `/api/synonyms`, `/api/rephrase` and styled `/api/alternatives`
return **503** and the UI hides the controls — the core translate flow is unaffected. The active
modes are listed under `styles` in `GET /api/health`. Override the model with `SUGGEST_MODEL`
(see [CONFIGURATION.md](CONFIGURATION.md)).

---

See also: [CONFIGURATION.md](CONFIGURATION.md) · [QUALITY.md](QUALITY.md) ·
[DEVELOPMENT.md](DEVELOPMENT.md) · [ARCHITECTURE.md](ARCHITECTURE.md)
