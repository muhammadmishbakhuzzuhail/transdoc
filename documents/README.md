# Test Documents (all real downloads)

Categorized real-world inputs for testing the pipeline. **No synthetic/manual files** —
every file fetched from a public source. Synthetic ground-truth samples live in `../samples/`.

| Folder | Case | Files | Source |
|--------|------|-------|--------|
| `digital_text/` | born-digital PDF, multi-column | arxiv_attention_en, arxiv_bert_en | arXiv |
| `multilingual/` | digital PDF, non-Latin text layer | UDHR en/zh/ru/ja/ko/ar | OHCHR + ar.wikipedia |
| `scanned_pdf/` | **machine scan → PDF, no text layer (OCR path)** | udhr_hindi_scan, udhr_thai_scan | OHCHR (image-based PDFs) |
| `full_image/` | **document IS an image** (jpg/png) | us_constitution, magna_carta, diamond_sutra (zh), manuscript_arabic, document_chinese, letter_handwritten, typed_letter, newspaper_scan | Wikimedia Commons |
| `forms/` | official forms (fields, tables, checkboxes) | irs_w9, irs_1040 | irs.gov |

## Coverage of input cases
- ✅ Clean digital text (digital_text, multilingual)
- ✅ Scanned PDF, image-only → OCR (scanned_pdf: Hindi/Thai, genuinely 0 text layer)
- ✅ Document as raw image → OCR (full_image)
- ✅ Non-Latin scripts: Arabic (RTL), CJK, Cyrillic, Devanagari, Thai
- ✅ Handwriting (full_image/letter_handwritten)
- ✅ Historical/degraded (magna_carta, diamond_sutra, newspaper)
- ✅ Forms with fields/tables (forms/)

## Re-download
See git history / the download commands in the project notes. All URLs are public; the
Wikimedia ones use `Special:FilePath` or the Commons API with a `User-Agent` header.
