# transdoc — clone & run. Replaces the manual venv juggling.
#
#   make setup        backend .venv + frontend deps (the everyday path; CPU, no paddle)
#   make setup-layout isolated paddle venv for --layout (heavy: ~1.9 GB models, opt-in)
#   make test / lint / eval        backend checks
#   make serve        REST API on :8000      make dev   frontend dev server
#   make clean        remove venvs + caches
#
# Override the python or the paddle wheel:
#   make setup PYTHON=python3.12
#   make setup-layout PADDLE_PKG="paddlepaddle==3.3.1"   # pure-CPU wheel (no CUDA)
#
# OCR system deps (install via your package manager, not pip):
#   tesseract-ocr                          base engine
#   tesseract-ocr-script-{latn,grek,cyrl}  per-script models — read every language of a script,
#                                          far better than the lang packs (portuguese 3->0.04,
#                                          greek 2.7->1.5, russian 0.5->0.25 CER). Auto-preferred.
#   tesseract-ocr-{ell,ara,hin,...}        language-pack fallback when a script model isn't present

PYTHON     ?= python3.11
VENV       := backend/.venv
PY         := $(VENV)/bin/python
PIP        := $(VENV)/bin/pip
LAYOUT_VENV := backend/layout_venv
# The dev machine runs the GPU wheel (works on CPU too); CPU-only users override PADDLE_PKG.
PADDLE_PKG ?= paddlepaddle-gpu==3.3.1

.PHONY: setup setup-backend setup-frontend setup-layout test lint eval eval-baseline \
        eval-real eval-real-baseline eval-ocr eval-judge eval-translate eval-preserve eval-table eval-consistency eval-layout \
        eval-expansion eval-reading-order eval-typing serve dev clean

setup: setup-backend setup-frontend ## everyday dev setup (no paddle)

setup-backend:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	cd backend && .venv/bin/pip install -e ".[dev,formats,api]"
	@echo "backend ready -> $(PY)"

setup-frontend:
	cd frontend && npm ci
	@echo "frontend ready"

# Isolated paddle env for the structured/--layout path. paddlepaddle and torch can't share a
# venv (nccl symbol clash), so this lives apart and the backend bridges to it out-of-process
# (default search ./backend/layout_venv/bin/python, or set TRANSDOC_LAYOUT_PYTHON).
setup-layout:
	$(PYTHON) -m venv $(LAYOUT_VENV)
	$(LAYOUT_VENV)/bin/pip install --upgrade pip
	$(LAYOUT_VENV)/bin/pip install "$(PADDLE_PKG)"
	$(LAYOUT_VENV)/bin/pip install paddleocr==3.7.0 paddlex==3.7.1
	cd backend && layout_venv/bin/pip install -e .
	@echo "layout venv ready -> $(LAYOUT_VENV)/bin/python  (use --layout paddle / layout=auto)"

test:
	cd backend && .venv/bin/pytest

lint:
	cd backend && .venv/bin/ruff check src tests

# Regression gate over the committed digital fixtures (what CI runs).
eval:
	cd backend && .venv/bin/python -m transdoc.eval.harness src/transdoc/eval/samples \
		--engine echo --baseline src/transdoc/eval/baseline.json

# Rebuild the fixtures + baseline (only when the fixtures or metrics change).
eval-baseline:
	cd backend && .venv/bin/python -m transdoc.eval.fixtures src/transdoc/eval/samples
	cd backend && .venv/bin/python -m transdoc.eval.harness src/transdoc/eval/samples \
		--engine echo --out src/transdoc/eval/baseline.json

# Structure-only regression gate over the REAL corpus (23 digital docs: arXiv, IRS forms, UDHR
# in 16 languages incl. RTL, a PPTX) vs the committed baseline. Local/opt-in — the corpus is
# git-ignored, so fetch it first: `cd backend && scripts/fetch_corpus.sh`. OCR-only dirs and
# font-sensitive render metrics are excluded so the gate is reproducible (echo, no network).
eval-real:
	cd backend && TRANSDOC_LAYOUT_DISABLE=1 TRANSDOC_TM_DISABLE=1 .venv/bin/python \
		-m transdoc.eval.harness corpus/real --engine echo \
		--baseline corpus/baseline_real.json \
		--exclude-dir full_image --exclude-dir scanned_pdf --structure-only

# Translation quality (chrF) vs the FLORES-200 benchmark — translates the English dev set through
# the engine and scores against the professional reference. Downloads FLORES-200 on first run
# (set FLORES_DIR to reuse). Online (the engine is online). Pass langs/N via ARGS.
#   make eval-translate ARGS="--n 100 fr de ja ar"
eval-translate:
	cd backend && .venv/bin/python -m scripts.eval_translate $(ARGS)

# Entity preservation: do numbers/URLs/emails/dates/prices/codes survive translation verbatim?
# The accuracy that matters for a document translator (a mangled account number > an awkward
# sentence). Runs curated cases through the full translate path. Online. Pass langs/--show via ARGS.
#   make eval-preserve ARGS="--show fr ar ja"
eval-preserve:
	cd backend && .venv/bin/python -m scripts.eval_preserve $(ARGS)

# Table-structure accuracy (TEDS-Struct) vs <stem>.tables.html reference sidecars — scores the
# extracted grid (rows/cells/spans), which the cell-count gate can't. Bring your own references.
#   make eval-table ARGS="path/to/doc.pdf"
eval-table:
	cd backend && .venv/bin/python -m scripts.eval_table $(ARGS)

# Layout region accuracy: IoU + detection P/R/F1 + label accuracy vs <stem>.layout.json refs —
# scores whether regions are in the right places with the right types (counts can't). BYO refs.
#   make eval-layout ARGS="path/to/doc.pdf"
eval-layout:
	cd backend && .venv/bin/python -m scripts.eval_layout $(ARGS)

# Reading-order accuracy (Area D): XY-cut order vs <stem>.order.json refs (boxes in reading
# order) — Kendall-tau + sequence accuracy. What eval-layout (IoU/label) can't measure. BYO refs.
#   make eval-reading-order ARGS="path/to/doc.pdf"
eval-reading-order:
	cd backend && .venv/bin/python -m scripts.eval_reading_order $(ARGS)

# Block-typing accuracy (Area D): final IR block types vs <stem>.types.json refs (type+bbox) —
# overall accuracy + per-type P/R + confusion. Scores the running-head/footer/page-number pass +
# heuristic/PP typing. BYO refs. Add --show for the per-type breakdown.
#   make eval-typing ARGS="--show path/to/doc.pdf"
eval-typing:
	cd backend && .venv/bin/python -m scripts.eval_typing $(ARGS)

# Text-expansion fidelity (Area C): simulate target-language expansion (pad each block ~1.4x),
# reconstruct the PDF, and count illegible/tiny/overflow spans + page spill. Deterministic/offline
# (no engine). BYO corpus of text-layer PDFs. --baseline gates regressions.
#   make eval-expansion ARGS="corpus/real/multilingual/*.pdf"
#   make eval-expansion ARGS="--baseline corpus/baseline_expansion.json corpus/real/**/*.pdf"
eval-expansion:
	cd backend && .venv/bin/python -m scripts.eval_expansion $(ARGS)

# Terminology consistency: does a repeated term get the same target rendering across contexts?
# (1.0 = consistent.) Measure-before-build for glossary auto-extraction. Online. Pass langs via ARGS.
#   make eval-consistency ARGS="fr de id"
eval-consistency:
	cd backend && .venv/bin/python -m scripts.eval_consistency $(ARGS)

# Translation QA-rate: run curated entity-dense sentences through the full translate path, then the
# rule-based QA suite (entity/placeholder/untranslated/empty/length/glossary). Reports HARD findings
# per language (0 = all entities preserved). Online (real engine). Pass langs/--show/--engine via ARGS.
#   make eval-qa ARGS="--show fr ar ja"
eval-qa:
	cd backend && .venv/bin/python -m scripts.eval_qa $(ARGS)

# LLM-as-judge: Claude vision scores extraction vs the source image (automates the manual
# vision-QA audit). Needs ANTHROPIC_API_KEY + the [llm] extra. Online + costs tokens.
#   make eval-judge ARGS="corpus/real/full_image/newspaper_scan.jpg corpus/real/multilingual/udhr_english.pdf"
eval-judge:
	cd backend && .venv/bin/python -m scripts.eval_judge $(ARGS)

# Rebuild the real-corpus baseline (after an intended extraction change; fetch the corpus first).
eval-real-baseline:
	cd backend && TRANSDOC_LAYOUT_DISABLE=1 TRANSDOC_TM_DISABLE=1 .venv/bin/python \
		-m transdoc.eval.harness corpus/real --engine echo \
		--exclude-dir full_image --exclude-dir scanned_pdf --structure-only \
		--out corpus/baseline_real.json

# OCR accuracy (CER/WER) with EXACT ground truth: rasterize text-bearing UDHR PDFs to image-only
# "scans", OCR them, score vs the source text layer. Latin/Cyrillic/Greek; fetch the corpus first.
# Add --layout auto to measure the PP-StructureV3 path instead of the Tesseract baseline.
eval-ocr:
	cd backend && .venv/bin/python -m scripts.eval_ocr

serve:
	cd backend && .venv/bin/transdoc serve

dev:
	cd frontend && npm run dev

clean:
	rm -rf $(VENV) $(LAYOUT_VENV) frontend/node_modules
	find backend -name __pycache__ -type d -prune -exec rm -rf {} +
