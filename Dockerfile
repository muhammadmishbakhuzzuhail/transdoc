# transdoc — single-image build: FastAPI serves the built React UI + REST API on one port.
# Build context is the repo root:   docker build -t transdoc .
# Run:                              docker run --rm -p 8000:8000 transdoc   -> http://localhost:8000
#
# Bundles Tesseract (OCR) + LibreOffice (office<->PDF, legacy .doc/.rtf). The structured layout
# path (PaddleOCR PP-StructureV3, ~1.9 GB) is NOT in the base image — the pipeline falls back to
# the heuristic extractor automatically when paddle is absent. Default engine is the Google web
# endpoint, so a running container needs outbound network for translation.

# ---- stage 1: build the React frontend ----
FROM node:20-slim AS web
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build                       # -> /fe/dist (relative API base => same-origin)

# ---- stage 2: python runtime ----
FROM python:3.12-slim AS app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TRANSDOC_HOST=0.0.0.0 \
    TRANSDOC_PORT=8000

# OCR (tesseract + OSD + a common language set), office<->PDF (LibreOffice core apps),
# libmagic for python-magic, Noto fonts for LibreOffice rendering of non-Latin scripts.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-osd \
        tesseract-ocr-eng tesseract-ocr-deu tesseract-ocr-fra tesseract-ocr-spa \
        tesseract-ocr-ita tesseract-ocr-por tesseract-ocr-nld \
        tesseract-ocr-chi-sim tesseract-ocr-jpn tesseract-ocr-kor \
        tesseract-ocr-ara tesseract-ocr-hin tesseract-ocr-rus \
        libreoffice-writer libreoffice-calc libreoffice-impress \
        libmagic1 fonts-noto-core fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/ ./backend/
# Reproducible install: pinned + hashed deps from the committed lock export (api + formats extras),
# then the transdoc package itself with no dependency re-resolution. Regenerate the export with:
#   cd backend && uv export --frozen --no-dev --no-emit-project --extra api --extra formats \
#     -o requirements-docker.txt
RUN pip install --require-hashes -r backend/requirements-docker.txt \
    && pip install --no-deps ./backend

# Bundle the built SPA so FastAPI serves it at / (and /assets via the StaticFiles mount).
COPY --from=web /fe/dist/ ./backend/src/transdoc/api/spa/

# Run as an unprivileged user: the image binds 0.0.0.0 with no auth, so a soffice/tesseract/paddle
# RCE or container escape must not land as root. The app writes jobs under the work dir and
# LibreOffice needs a writable HOME for its profile — give the user both.
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /var/lib/transdoc \
    && chown -R app:app /app /var/lib/transdoc
ENV HOME=/home/app \
    TRANSDOC_JOBS_DIR=/var/lib/transdoc/jobs
USER app

EXPOSE 8000
WORKDIR /app/backend
# Liveness for orchestrators (no curl in the image — use the stdlib).
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/health', timeout=4).status==200 else 1)"]
CMD ["python", "server.py"]
