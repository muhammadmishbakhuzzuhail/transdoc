# Translation Engine — No-API / Offline Research

Verified deep-research synthesis (2025–2026), adversarially checked. Goal: accurate
translation **without any API key**, self-hosted, fitting a 6GB GPU with CPU fallback.
**Coverage is universal — any language to any language, like DeepL — not country-specific.**
That requirement is decisive: it favors a single broad-coverage NMT model over per-pair models.

## What DeepL actually uses (and why you can't fully match it offline)
- Custom-topology transformer; since **July 2024**, a proprietary **in-house LLM tuned for
  translation** (built on a 544×H100 SuperPOD), coexisting with the classic NMT engine. `[high]`
- The real moat is **NOT architecture** — it's **proprietary quality-assessed data**
  (Linguee crawler, ~1B human translations) + **thousands of human language experts who
  "tutor" the model via RLHF**. `[high]`
- The architecture is replicable with open models; the curated data + human pipeline is not.
  DeepL's "1.4×–1.7× better" is self-reported marketing, not a FLORES/WMT benchmark. `[medium]`
- **Takeaway:** an open offline stack can get *good*, not DeepL-identical. Close the gap with
  glossary/TM + (optional) domain fine-tuning, not by chasing their architecture.

## Open offline engines (verified)
| Engine | Coverage | id/zh/ar | License | 6GB fit | Notes |
|--------|----------|----------|---------|---------|-------|
| **NLLB-200** distilled 600M / 1.3B | 200+ langs, 40k directions | ✅ all | **CC-BY-NC** ✗ | ✅ 600M ~2.4GB fp16, less int8 | best id quality, broad — **non-commercial only** |
| **MADLAD-400-3B** | 450+ langs | ✅ all | **Apache-2.0** ✓ | ⚠️ ~3GB int8 (3B is smallest) | commercial-safe broad-coverage default |
| **Opus-MT / Marian** | per-pair | ✅ en↔id exists | **MIT** ✓ | ✅ tiny | per-pair, CTranslate2-native, fast on CPU |
| **M2M-100 / SeamlessM4T** | many | partial | mixed/CC-BY-NC | varies | NLLB generally supersedes |
| **Tower+ / ALMA-R** (translation LLMs) | ~10–22 high-resource | ❌ **id & ar NOT covered** | varies | ⚠️ quantized | rivals GPT-4o on en↔zh etc., **not for Indonesian** |
| **CTranslate2 int8** | — | — | — | ✅ enabler | ~99–100% of FP32 BLEU, 2–8× speedup, **CPU + GPU** |

### Key verified conclusions
- Specialized translation LLMs (ALMA/Tower) match closed SOTA **only on high-resource pairs
  that exclude Indonesian and Arabic** → for id/ar, **dedicated NMT wins**. `[high]`
- "LLM beats NMT across the board" claims were **refuted**. Honest position: LLMs win/tie on
  high-resource pairs; NMT wins on coverage, low-resource, and footprint. `[medium]`
- **CTranslate2 int8** is the load-bearing enabler for running NMT on 6GB / CPU. `[high]`

## Recommendation for transdoc (universal coverage, no API, free deploy)
Universal any→any coverage rules out per-pair Opus-MT as the *primary* engine (managing
1000s of pair models is impractical) and rules out translation LLMs (Tower/ALMA cover only
~10–22 high-resource languages). A single broad multilingual NMT is the right core.

1. **Default (broadest coverage + best quality): NLLB-200-distilled** (600M or 1.3B) via
   CTranslate2 int8. **200+ languages**, one model, fits 6GB / CPU → free-deploy friendly.
   Engine: `nllb`. ⚠️ License **CC-BY-NC** → personal / research / non-commercial self-host only.
2. **Commercial / open-source ship (broad, Apache-2.0): MADLAD-400-3B.** 450+ languages, one
   model, int8 via CTranslate2. Heavier (3B) but commercial-safe. Engine: `madlad` — to add.
3. **Fast path for top pairs: Opus-MT/Marian (MIT).** Tiny, CPU-fast; use as an optional
   accelerator for the most common pairs, with NLLB/MADLAD as the universal fallback. Engine: `opusmt`.
4. **Optional quality upgrade (high-resource pairs only, has GPU): Tower+ 9B / ALMA-R** quantized.
5. **License fork:** the only real decision is commercial vs not. Non-commercial → NLLB (best).
   Commercial → MADLAD-400 (broad) + Opus-MT (fast common pairs). Both API-free.

### Free deployment
- Engine must run on **CPU** to be free → use NMT int8 (NLLB/Opus-MT/MADLAD), **not local LLM**.
- Hosting: **Oracle Cloud Always Free** (4 ARM + 24GB RAM, always-on) for self-host; or
  **HuggingFace Spaces** (free CPU) for a public demo. GPU is rarely free.
- Tradeoff: OCR (Surya) wants GPU → on free CPU you fall back to Tesseract (weaker on
  scans/non-Latin). Layout/table/image regeneration is pure CPU → unaffected.

## Text expansion → layout (the skeptic's concern, confirmed real)
Translation changes length: **EN→ID +20–30%**, EN→DE up to +35%, short UI strings +100–200%;
CJK→EN shrinks. This breaks **fixed-geometry (overlay) output**, not flow output.
- **Flow mode (DOCX/MD/HTML):** text reflows, rows/pages grow → expansion is a non-issue.
  Best for editable targets.
- **Layout mode (PDF overlay):** handled by `insert_htmlbox(scale_low=0)` auto-shrinking text
  to the original bbox; if it must shrink below 60% the block is **flagged** for review
  (`text_expansion` flag) rather than silently degraded. Images are untouched; table cells
  shrink per-cell.

## Formatting tags / glossary
- Wrap inline placeholders/tags and instruct the engine to keep them verbatim; for NMT, mask
  tags to sentinel tokens before translating and restore after.
- Glossary enforced post-translation (longest-term-first replace) for all engines; LLM engines
  also receive the glossary in-prompt. See `translate/base.py::_apply_glossary`.

_Sources: deepl.com (how-deepl-works, next-gen-llm, fp8-training), PR Newswire, Fortune,
Slator; NLLB Nature 2024 + arXiv; MADLAD-400 (Google); Opus-MT/Marian (Helsinki-NLP);
ALMA (ICLR 2024); Tower/Tower+ (Unbabel); CTranslate2/OpenNMT docs._
