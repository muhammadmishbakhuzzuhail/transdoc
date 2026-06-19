# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""IndicTrans2 translator — offline neural MT for 22 scheduled Indic languages (multi-script).

LICENSE: AI4Bharat IndicTrans2 weights are MIT (commercial-safe), unlike NLLB (CC-BY-NC). This
closes the Indic-language gap the CPU-stack research flagged. Direction picks the right model:
English↔Indic and Indic↔Indic each have their own checkpoint. Distilled checkpoints are the
CPU-viable default; override with INDICTRANS_* env vars for the full 1B models.

Needs `transformers` + `torch` and the `IndicTransToolkit` (IndicProcessor) for the script
normalization / entity handling the models were trained with — installed via the `[indic]` extra.
Lazily loaded so importing this module is cheap and the rest of the app never pays for it.
"""

from __future__ import annotations

from ..config import Config

# ISO 639-1 -> IndicTrans2 (FLORES-style) code. English is the pivot/non-Indic side.
INDIC_CODE = {
    "en": "eng_Latn",
    "hi": "hin_Deva", "bn": "ben_Beng", "ta": "tam_Taml", "te": "tel_Telu",
    "ml": "mal_Mlym", "kn": "kan_Knda", "gu": "guj_Gujr", "pa": "pan_Guru",
    "mr": "mar_Deva", "or": "ory_Orya", "as": "asm_Beng", "ur": "urd_Arab",
    "ne": "npi_Deva", "si": "sin_Sinh", "sd": "snd_Arab", "ks": "kas_Arab",
    "sa": "san_Deva", "mai": "mai_Deva", "kok": "gom_Deva", "mni": "mni_Mtei",
    "doi": "doi_Deva", "brx": "brx_Deva", "sat": "sat_Olck",
}

_EN = "eng_Latn"
# Distilled (CPU-viable) defaults; override for the 1B full models.
_MODELS = {
    "en-indic": "ai4bharat/indictrans2-en-indic-dist-200M",
    "indic-en": "ai4bharat/indictrans2-indic-en-dist-200M",
    "indic-indic": "ai4bharat/indictrans2-indic-indic-dist-320M",
}


def to_code(lang: str | None, default: str = _EN) -> str:
    """ISO 639-1 -> IndicTrans2 code; unknown / auto -> default (English)."""
    if not lang or lang == "auto":
        return default
    return INDIC_CODE.get(lang, default)


def direction(src_code: str, tgt_code: str) -> str:
    """Which checkpoint family translates src->tgt."""
    s_indic, t_indic = src_code != _EN, tgt_code != _EN
    if s_indic and t_indic:
        return "indic-indic"
    if s_indic and not t_indic:
        return "indic-en"
    return "en-indic"          # en->indic (and the en->en edge case)


class IndicTransTranslator:
    name = "indictrans"
    _cache: dict = {}          # direction -> (tokenizer, model, processor)

    def _load(self, dir_key: str):
        if dir_key in IndicTransTranslator._cache:
            return IndicTransTranslator._cache[dir_key]
        import os

        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        try:
            from IndicTransToolkit.processor import IndicProcessor
        except Exception as e:  # pragma: no cover - depends on optional extra
            raise RuntimeError(
                "IndicTrans2 needs the IndicTransToolkit — install the '[indic]' extra "
                "(pip install -e '.[indic]')") from e

        name = os.environ.get(f"INDICTRANS_{dir_key.replace('-', '_').upper()}", _MODELS[dir_key])
        tok = AutoTokenizer.from_pretrained(name, trust_remote_code=True)
        kwargs = {"trust_remote_code": True}
        if torch.cuda.is_available():
            kwargs["torch_dtype"] = torch.float16
        model = AutoModelForSeq2SeqLM.from_pretrained(name, **kwargs)
        if torch.cuda.is_available():
            model = model.to("cuda")
        proc = IndicProcessor(inference=True)
        IndicTransTranslator._cache[dir_key] = (tok, model, proc)
        return IndicTransTranslator._cache[dir_key]

    def translate_batch(self, texts: list[str], cfg: Config,
                        src: str | None = None) -> list[str]:
        if not texts:
            return []
        import torch

        src_code = to_code(src, _EN)
        tgt_code = to_code(cfg.target_lang, _EN)
        tok, model, ip = self._load(direction(src_code, tgt_code))

        out: list[str] = []
        CHUNK = 16
        for i in range(0, len(texts), CHUNK):
            batch = texts[i:i + CHUNK]
            prepared = ip.preprocess_batch(batch, src_lang=src_code, tgt_lang=tgt_code)
            enc = tok(prepared, return_tensors="pt", padding=True, truncation=True,
                      max_length=256)
            enc = {k: v.to(model.device) for k, v in enc.items()}
            with torch.no_grad():
                gen = model.generate(**enc, max_length=256, num_beams=5,
                                     no_repeat_ngram_size=3, length_penalty=1.0)
            decoded = tok.batch_decode(gen, skip_special_tokens=True)
            out.extend(ip.postprocess_batch(decoded, lang=tgt_code))
        return out
