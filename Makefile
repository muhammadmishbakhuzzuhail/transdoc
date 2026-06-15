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
#   tesseract-ocr-script-latn              Latin script model — reads diacritics (ç/ã/é/...) the
#                                          bare eng pack drops (portuguese CER 3% -> 0.04%)
#   tesseract-ocr-{ell,ara,...}            per-script packs for non-Latin scans

PYTHON     ?= python3.11
VENV       := backend/.venv
PY         := $(VENV)/bin/python
PIP        := $(VENV)/bin/pip
LAYOUT_VENV := backend/layout_venv
# The dev machine runs the GPU wheel (works on CPU too); CPU-only users override PADDLE_PKG.
PADDLE_PKG ?= paddlepaddle-gpu==3.3.1

.PHONY: setup setup-backend setup-frontend setup-layout test lint eval eval-baseline \
        eval-real eval-real-baseline eval-ocr eval-judge eval-translate eval-preserve \
        serve dev clean

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
