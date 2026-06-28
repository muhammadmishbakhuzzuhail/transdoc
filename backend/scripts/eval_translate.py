# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Translation-quality eval: chrF against the FLORES-200 benchmark.

FLORES-200 is the standard multilingual MT benchmark — 997 dev sentences professionally
translated into 200+ languages, all parallel. This translates the English source through the
pipeline's engine and scores the output against the FLORES reference with chrF, per language.
Unlike CER/WER (which measures OCR), this measures *translation* quality.

Needs network (the engine is online by default) and the FLORES-200 dev set. The dev set is
downloaded + cached on first run (set FLORES_DIR to reuse an existing copy). Local/opt-in like
the other eval tools.

    cd backend && .venv/bin/python -m scripts.eval_translate                  # default langs, 50 sents
    cd backend && .venv/bin/python -m scripts.eval_translate --n 100 fr de ja
    cd backend && .venv/bin/python -m scripts.eval_translate --engine google

Note: chrF here is the harness's mean sentence-level chrF (char n-gram F2), not sacrebleu's
corpus chrF — consistent for tracking the pipeline over time, not directly comparable to
published sacrebleu numbers.
"""

from __future__ import annotations

import os
import sys
import tarfile
import urllib.request
from pathlib import Path

# Google target code -> FLORES-200 dev file stem. Latin, Cyrillic, Greek, Arabic, Indic, CJK,
# Thai — a spread of scripts so a regression in any script family shows up.
LANGS: dict[str, str] = {
    "fr": "fra_Latn", "de": "deu_Latn", "es": "spa_Latn", "pt": "por_Latn",
    "id": "ind_Latn", "vi": "vie_Latn", "ru": "rus_Cyrl", "el": "ell_Grek",
    "ar": "arb_Arab", "hi": "hin_Deva", "bn": "ben_Beng", "th": "tha_Thai",
    "zh-CN": "zho_Hans", "ja": "jpn_Jpan", "ko": "kor_Hang",
}
_SRC_FLORES = "eng_Latn"
_URL = "https://dl.fbaipublicfiles.com/nllb/flores200_dataset.tar.gz"


def flores_dir() -> Path:
    """Return the FLORES-200 directory containing dev/<code>.dev, downloading + caching it on
    first run. Override with FLORES_DIR (pointing at an extracted flores200_dataset)."""
    env = os.environ.get("FLORES_DIR")
    if env:
        return Path(env)
    cache = Path("corpus") / "flores200_dataset"
    if (cache / "dev" / f"{_SRC_FLORES}.dev").exists():
        return cache
    cache.parent.mkdir(parents=True, exist_ok=True)
    tgz = cache.parent / "flores200_dataset.tar.gz"
    if not tgz.exists():
        sys.stderr.write(f"downloading FLORES-200 ({_URL}) ...\n")
        urllib.request.urlretrieve(_URL, tgz)   # noqa: S310 — fixed, trusted dataset URL
    with tarfile.open(tgz) as t:
        t.extractall(cache.parent, filter="data")
    return cache


def _lines(path: Path, n: int) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()[:n]


def main(argv: list[str]) -> int:
    from transdoc.config import Config, Engine
    from transdoc.eval.dashboard import append_history
    from transdoc.eval.metrics import chrf, sacrebleu_bleu, sacrebleu_chrf
    from transdoc.translate import get_translator

    engine = "google"
    n = 50
    worst = 0
    args = list(argv)
    for flag, cast in (("--engine", str), ("--n", int), ("--show-worst", int)):
        if flag in args:
            i = args.index(flag)
            val = cast(args[i + 1])
            args = args[:i] + args[i + 2:]
            if flag == "--engine":
                engine = val
            elif flag == "--n":
                n = val
            else:
                worst = val
    bad = [k for k in args if k not in LANGS]
    if bad:
        sys.stderr.write(f"unknown lang code(s): {bad}; known: {sorted(LANGS)}\n")
        return 2
    langs = {k: LANGS[k] for k in args} if args else LANGS

    try:
        root = flores_dir()
    except Exception as e:
        sys.stderr.write(f"FLORES-200 unavailable ({type(e).__name__}: {e}). Set FLORES_DIR.\n")
        return 1
    dev = root / "dev"
    src = _lines(dev / f"{_SRC_FLORES}.dev", n)

    # sacrebleu (if installed) gives the publishable corpus-level chrF/BLEU with a reproducible
    # signature; the in-house mean chrF stays as the fast, dependency-free tracking number.
    have_sb = sacrebleu_chrf(["x"], ["x"]) is not None
    print(f"Translation chrF vs FLORES-200 (engine={engine}, n={n} sentences)")
    print("sacrebleu corpus chrF/BLEU shown when available; in-house mean chrF always.\n"
          if have_sb else "(install sacrebleu for publishable corpus chrF/BLEU)\n")
    print(f"{'lang':8} {'code':10} {'chrF':>6} {'sbchrF':>7} {'sbBLEU':>7}")
    print("-" * 42)
    scores = []
    per_lang: dict[str, float] = {}
    for gcode, fcode in langs.items():
        ref_path = dev / f"{fcode}.dev"
        if not ref_path.exists():
            print(f"{gcode:8} {fcode:10} {'(no ref)':>6}")
            continue
        refs = _lines(ref_path, n)
        cfg = Config(target_lang=gcode, source_lang="en", engine=Engine(engine))
        try:
            hyps = get_translator(cfg).translate_batch(src, cfg, src="en")
        except Exception as e:
            print(f"{gcode:8} {fcode:10} ERROR {type(e).__name__}: {e}")
            continue
        pair = [(r, h, chrf(r, h)) for r, h in zip(refs, hyps) if r.strip()]
        score = sum(c for _, _, c in pair) / len(pair) if pair else 0.0
        scores.append(score)
        per_lang[gcode] = round(score, 2)
        kept_refs = [r for r, _, _ in pair]
        kept_hyps = [h for _, h, _ in pair]
        sb_c = sacrebleu_chrf(kept_refs, kept_hyps)
        sb_b = sacrebleu_bleu(kept_refs, kept_hyps)
        print(f"{gcode:8} {fcode:10} {score:>6.1f} "
              f"{(f'{sb_c:.1f}' if sb_c is not None else '-'):>7} "
              f"{(f'{sb_b:.1f}' if sb_b is not None else '-'):>7}")
        if worst:
            # error analysis: the lowest-chrF sentences are where the engine/pipeline loses most
            for r, h, c in sorted(pair, key=lambda t: t[2])[:worst]:
                print(f"   [{c:4.1f}] ref: {r[:110]}")
                print(f"          hyp: {h[:110]}")
    if scores:
        mean = sum(scores) / len(scores)
        print("-" * 42)
        print(f"{'mean':8} {'':10} {mean:>6.1f}")
        # record the run on the quality time-series so the trend (and the numbers) live in-repo
        append_history({"date": _today(), "engine": engine, "kind": "flores",
                        "metric": "chrf_inhouse", "overall": round(mean, 2),
                        "scores": per_lang, "n": n})
        print("appended to eval/history.jsonl")
    return 0


def _today() -> str:
    import datetime
    return datetime.date.today().isoformat()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
