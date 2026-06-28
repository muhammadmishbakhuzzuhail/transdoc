# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Head-to-head engine benchmark on FLORES-200 (the free competitor comparison).

Translates the FLORES-200 English source through several engines and scores each against the FLORES
gold reference per language pair, with sacrebleu corpus chrF (+ reference-based COMET when the
`comet` package is available). This is the *free* head-to-head — our own engines (online endpoint +
offline NMT) on a public gold benchmark; paid DeepL/Google-Cloud are out of scope (no key/cost).
It proves the QE-engine-selection thesis: different engines win different pairs.

Needs the FLORES-200 dev set (auto-downloaded by scripts.eval_translate's flores_dir) and the
engines' models. Run manually on GPU, never in CI.

    cd backend && .venv/bin/python -m scripts.bench_vs_engines --engines google,opusmt,nllb \
        --langs de,hi,id --n 30
"""

from __future__ import annotations

import sys

from scripts.eval_translate import _SRC_FLORES, LANGS, _lines, flores_dir
from transdoc.eval.bench import best_per_lang, render_markdown, score_matrix
from transdoc.eval.dashboard import append_history
from transdoc.eval.metrics import sacrebleu_bleu, sacrebleu_chrf


def _arg(argv, flag, default):
    return argv[argv.index(flag) + 1] if flag in argv else default


def _comet_da_scorer():
    """Return fn(srcs, refs, hyps)->mean reference-based COMET, or None if comet is unavailable.
    Separate from the QE model in quality.py: this is wmt22-comet-da (uses the gold reference)."""
    try:
        from comet import download_model, load_from_checkpoint
        model = load_from_checkpoint(download_model("Unbabel/wmt22-comet-da"))
    except Exception as e:
        sys.stderr.write(f"reference COMET unavailable ({type(e).__name__}: {e}); chrF/BLEU only\n")
        return None

    def _score(srcs, refs, hyps):
        try:
            import torch
            gpus = 1 if torch.cuda.is_available() else 0
        except Exception:
            gpus = 0
        data = [{"src": s, "mt": h, "ref": r} for s, h, r in zip(srcs, hyps, refs)]
        return float(model.predict(data, batch_size=8, gpus=gpus)["system_score"])

    return _score


def main(argv: list[str]) -> int:
    from transdoc.config import Config, Engine
    from transdoc.translate import get_translator

    engines = _arg(argv, "--engines", "google,opusmt,nllb").split(",")
    langs = _arg(argv, "--langs", "de,hi,id").split(",")
    n = int(_arg(argv, "--n", "30"))
    bad = [x for x in langs if x not in LANGS]
    if bad:
        sys.stderr.write(f"unknown lang(s): {bad}; known: {sorted(LANGS)}\n")
        return 2

    root = flores_dir()
    dev = root / "dev"
    srcs = _lines(dev / f"{_SRC_FLORES}.dev", n)
    src_by_lang = {lang: srcs for lang in langs}
    ref_by_lang = {lang: _lines(dev / f"{LANGS[lang]}.dev", n) for lang in langs}

    comet = None if "--no-comet" in argv else _comet_da_scorer()

    cache: dict[tuple[str, str], list[str]] = {}

    def translate_fn(engine: str, lang: str, texts: list[str]) -> list[str]:
        if (engine, lang) in cache:          # so the COMET pass reuses, not re-translates
            return cache[(engine, lang)]
        cfg = Config(target_lang=lang, source_lang="en", engine=Engine(engine))
        tr = get_translator(cfg)
        try:
            hyps = tr.translate_batch(texts, cfg, src="en")
        finally:
            rel = getattr(tr, "release", None)
            if callable(rel):
                rel()
        cache[(engine, lang)] = hyps
        return hyps

    metric_fns = {
        "chrf": sacrebleu_chrf,
        "bleu": sacrebleu_bleu,
    }
    # chrf/BLEU need only (refs, hyps); COMET is added per cell below because it also needs srcs.
    # translate_fn memoises, so the COMET pass reuses the same hypotheses rather than re-translating.
    matrix = score_matrix(langs, engines, src_by_lang, ref_by_lang, translate_fn, metric_fns)
    if comet:
        for lang in langs:
            for eng in engines:
                cell = matrix[lang].get(eng, {})
                if "error" in cell:
                    continue
                try:
                    hyps = translate_fn(eng, lang, src_by_lang[lang])
                    cell["comet"] = round(comet(src_by_lang[lang], ref_by_lang[lang], hyps), 2)
                except Exception as e:
                    sys.stderr.write(f"comet {lang}/{eng} failed: {e}\n")

    print(f"\nHead-to-head on FLORES-200 (n={n} sentences, gold reference)\n")
    print(render_markdown(matrix, engines, metric="chrf"))
    if comet:
        print()
        print(render_markdown(matrix, engines, metric="comet"))

    # record the run on the quality time-series (one row per lang, chrf of the winning engine)
    winners = best_per_lang(matrix, "chrf")
    append_history({"date": _today(), "kind": "head2head", "metric": "sacrebleu_chrf",
                    "engines": engines, "scores": winners,
                    "overall": _winner_mean(matrix, winners, "chrf"), "n": n,
                    "note": "FLORES-200 gold; free head-to-head (own engines), not DeepL/Google-Cloud"})
    print("\nappended to eval/history.jsonl")
    return 0


def _winner_mean(matrix, winners, metric):
    vals = [matrix[lang][eng][metric] for lang, eng in winners.items()
            if metric in matrix[lang].get(eng, {})]
    return round(sum(vals) / len(vals), 2) if vals else None


def _today() -> str:
    import datetime
    return datetime.date.today().isoformat()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
