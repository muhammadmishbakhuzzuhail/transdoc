# Test Corpus

Cases for the document-intelligence pipeline. Mix of real downloads + synthetic
(known ground-truth). Regenerate synthetic ones with `.venv/bin/python scripts/make_samples.py`.

| Case | File(s) | Tests |
|------|---------|-------|
| Digital PDF, multi-column | `digital_pdf/arxiv_attention_en.pdf` | layout, 2-col reading order, tables, formulas |
| Digital PDF, simple | `digital_pdf/{minimal,pdflatex_4pages,pdflatex_image}.pdf` | basic text+image extraction |
| Digital PDF, non-Latin | `multilingual/udhr_{arabic,chinese,japanese,korean,russian}.pdf` | RTL, CJK, Cyrillic text layer |
| **Scanned PDF (real)** | `multilingual/udhr_{hindi,thai}.pdf` | 0 text layer → OCR path (Devanagari, Thai) |
| **Scanned PDF (synthetic)** | `scanned_pdf/udhr_{english,russian}_scanned.pdf` | image-only PDF, OCR + layout rebuild |
| Image-only (doc = picture) | `image_only/text_{en,ru,zh,ja,ko,hi,ar}.png` | OCR per script, known ground-truth |
| Phone photo | `photo/photo_en.jpg` | deskew (-7°) + denoise + uneven lighting → OCR |
| DOCX structured | `docx/structured.docx` | headings, list, table, multilingual run |
| ODT structured | `odt/structured.odt` | ODT parse |

## Ground-truth (image_only / photo)
- en: `The quick brown fox jumps over the lazy dog. 1234567890.`
- ru: `Съешь же ещё этих мягких французских булок да выпей чаю.`
- zh: `快速的棕色狐狸跳过了那只懒狗。人工智能与机器翻译。`
- ja: `いろはにほへと ちりぬるを。機械翻訳のテストです。`
- ko: `다람쥐 헌 쳇바퀴에 타고파. 기계 번역 테스트입니다.`
- hi: `तेज़ भूरी लोमड़ी आलसी कुत्ते के ऊपर से कूद गई।`
- ar: `العربية لغة جميلة. الترجمة الآلية اختبار النص.`

## Layout-fidelity check
For "layout must not change": extract → translate → regenerate, then compare the
regenerated doc's structure (heading count, table dims, block order, page count)
against the source IR. See `tests/` (TODO once pipeline lands).
