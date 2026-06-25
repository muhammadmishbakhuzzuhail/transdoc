# Third-party notices

transdoc is distributed under the **GNU AGPL-3.0** (see [LICENSE](LICENSE)). It builds on the
third-party software, model weights, fonts and binaries listed below, each of which remains under
**its own license**. This list is best-effort and provided for attribution/compliance; always
verify the upstream license of any component you redistribute or deploy — **especially the
non-commercial model weights**, which are *opt-in* and not installed by default.

## Runtime Python dependencies (core)

| Project | Purpose | License (verify upstream) |
|---------|---------|---------------------------|
| [PyMuPDF](https://github.com/pymupdf/PyMuPDF) | PDF text/bbox/render + bundled Noto fonts | **AGPL-3.0** (compatible) |
| [pydantic](https://github.com/pydantic/pydantic) | config / data models | MIT |
| [typer](https://github.com/tiangolo/typer) | CLI | MIT |
| [rich](https://github.com/Textualize/rich) | terminal output | MIT |
| [python-magic](https://github.com/ahupp/python-magic) | MIME sniffing | MIT |
| [charset-normalizer](https://github.com/Ousret/charset_normalizer) | encoding detection | MIT |
| [python-docx](https://github.com/python-openxml/python-docx) | DOCX read/write | MIT |
| [odfpy](https://github.com/eea/odfpy) | ODT read/write | Apache-2.0 / GPL |
| [Pillow](https://github.com/python-pillow/Pillow) | image handling | MIT-CMU (HPND) |
| [pytesseract](https://github.com/madmaze/pytesseract) | Tesseract binding | Apache-2.0 |
| [Jinja2](https://github.com/pallets/jinja) | report templating | BSD-3-Clause |
| [langdetect](https://github.com/Mimino666/langdetect) | language detection | Apache-2.0 |
| [deep-translator](https://github.com/nidhaloff/deep-translator) | free MT chain | Apache-2.0 |
| [python-bidi](https://github.com/MeirKriheli/python-bidi) | RTL bidi reorder | LGPL-3.0+ |
| [arabic-reshaper](https://github.com/mpcabd/python-arabic-reshaper) | Arabic shaping | MIT |
| [defusedxml](https://github.com/tiran/defusedxml) | hardened XML (TMX) | PSF-2.0 |

## Optional Python dependencies

| Extra | Project | License (verify upstream) |
|-------|---------|---------------------------|
| `[suggest]` | [transformers](https://github.com/huggingface/transformers) | Apache-2.0 |
| `[suggest]` | [torch](https://github.com/pytorch/pytorch) | BSD-3-Clause |
| `[suggest]` | [accelerate](https://github.com/huggingface/accelerate) | Apache-2.0 |
| `[suggest]` | [bitsandbytes](https://github.com/TimDettmers/bitsandbytes) | MIT |

## Model weights (downloaded on demand — NOT bundled)

Some engines/features pull pretrained weights at runtime. **The following are non-commercial; use
them only if your deployment is non-commercial, or substitute a permissively-licensed model:**

| Model | Used by | License (verify upstream) |
|-------|---------|---------------------------|
| **NLLB-200** (Meta) | offline NMT (`-e nllb`) | **CC-BY-NC-4.0 (non-commercial)** |
| **Surya** | opt-in reading-order/layout | **non-commercial** — verify upstream |
| **Qwen2.5-3B-Instruct** | review suggestion layer (`[suggest]`) | **Qwen Research License (non-commercial)** — verify upstream |
| COMET-Kiwi (Unbabel) | reference-free QE (`--quality`) | verify upstream (model-specific) |
| PP-StructureV3 / PaddleOCR | structured layout extraction | Apache-2.0 |
| EasyOCR | OCR escalation | Apache-2.0 |

The **default** translation engine is the Google web endpoint (no local model), so a default
install pulls none of the non-commercial weights above.

## Bundled binaries & fonts (Docker image)

| Component | License (verify upstream) |
|-----------|---------------------------|
| [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) + language data | Apache-2.0 |
| [LibreOffice](https://www.libreoffice.org/) (office ↔ PDF) | MPL-2.0 / LGPL-3.0 |
| [Noto fonts](https://github.com/notofonts) | SIL Open Font License 1.1 |

If you spot an inaccuracy in this list, please open an issue — see [SECURITY.md](SECURITY.md) for
private reports.
