# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Professional-audit hardening: per-image OCR timeouts, COMET quality-pass skip on trivial docs,
  non-root Docker image with a healthcheck, job TTL reaper, hardened TMX import (defusedxml).
- Review suggestion layer: in-context synonyms, sentence rephrase, and register modes
  (professional / academic / friendly / concise) via an opt-in local instruct LLM (`[suggest]`).
- `version` exposed in `GET /api/health`; `transdoc.__version__` single-sourced from the package.
- Governance: `SECURITY.md`, `CODE_OF_CONDUCT.md`, `THIRD_PARTY_NOTICES.md`, this changelog.

### Changed
- README "Scope & limits" clarified: the project is AGPL-3.0 open source; the NLLB-200 / Surya /
  Qwen model weights are opt-in **non-commercial** extras, not bundled by default.

### Security
- Suggestion endpoints take the job GPU lock so the review LLM never co-resides with a translate
  job on a small GPU (CUDA OOM).
- Job errors no longer return full tracebacks over the API; job ids are 128-bit; the job work dir
  is created `0700`.

## [0.1.0]

Initial baseline: CPU-first document translation across PDF (digital + scanned), DOCX, ODT, legacy
DOC, PPTX, XLSX, EPUB, subtitles and images; layout-faithful PDF output (form overlay / reflow);
in-place Office round-trip; multi-engine translation (Google default, offline NLLB, local Ollama);
a quality pipeline (COMET-Kiwi QE, LLM escalation, word-alignment style transfer, OCR repair) and a
glossary / translation-memory / correction flywheel; a review-first web UI; and a single-image
Docker build serving the SPA + REST API.

[Unreleased]: https://github.com/muhammadmishbakhuzzuhail/transdoc/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/muhammadmishbakhuzzuhail/transdoc/releases/tag/v0.1.0
