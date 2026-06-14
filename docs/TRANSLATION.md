# Translation Engine — No-API / Offline Research

Verified deep-research synthesis (2025–2026), adversarially checked. Goal: the **highest-quality
translation on a local CPU-only machine** for **personal, non-commercial** use — no API key, no
GPU, no commercial/license constraints. **Coverage is universal — any language to any language,
like DeepL.** That favors a single broad-coverage NMT model (NLLB-200) over per-pair models.

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

**DECISION (settled by an actual benchmark, 2026-06-15):** default = plain **`google`**, no
fallback chain. A round-trip-chrF benchmark (`scripts/bench_engines.py`, 5 sentences ×
id/ar/zh/de) measured:

| lang | Google | NLLB-200-600M |
|---|---|---|
| id | 87.9 | 85.8 |
| ar | 84.0 | 86.6 |
| zh | 82.7 | 78.1 |
| de | 85.9 | 84.8 |
| **avg** | **85.1** | 83.8 |

Google wins on quality at CPU-viable model sizes, so it's the plain default — no backstop chain
(personal/low-volume + TM cache + Google's own retry make one unnecessary; `-e fallback` adds
MyMemory + LibreTranslate if you want it). NLLB-600M ≈ Google but offline/private — use
`-e nllb` when privacy matters. The options below only matter for **offline-better-than-Google**
or a **commercial fork** (re-run the benchmark before committing):
- **NLLB-200-1.3B / 3.3B** — bigger model may beat Google, but much slower on CPU. `-e nllb` + `NLLB_MODEL=`.
- **MADLAD-400-3B** (Apache-2.0, 450+ langs) — broad commercial-safe. Engine: `madlad`.
- **Opus-MT/Marian (MIT)** — tiny, CPU-fast for common pairs. Engine: `opusmt`.

### Local run (no hosting — runs on your machine)
- Engine runs on **CPU** via NLLB int8 (CTranslate2). No GPU, no server, no public demo —
  this is a local personal tool.
- OCR: PP-StructureV3 + Tesseract are CPU-viable (Surya optional). Layout/table/image
  regeneration is pure CPU.

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
