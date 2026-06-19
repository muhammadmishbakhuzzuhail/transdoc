# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Formal MT quality benchmark via round-trip back-translation + chrF.

For each target language: EN -> lang -> EN through the production engine, then score the
back-translation against the original with chrF (character n-gram F-score, reference-based,
no model download). Higher chrF = the meaning/wording survived the round trip better.

LIVE NETWORK: hits the real translation endpoint (Google web / fallback chain). Slow and
ToS-grey — run manually, never in CI. The persistent TM caches each segment so re-runs are
cheap.

    .venv/bin/python scripts/bench_quality.py            # default fallback chain
    TRANSDOC_BENCH_ENGINE=google .venv/bin/python scripts/bench_quality.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from transdoc.config import Config, Engine  # noqa: E402
from transdoc.translate import get_translator  # noqa: E402

SENTENCES = [
    "The quick brown fox jumps over the lazy dog near the river.",
    "Climate change threatens coastal cities with rising sea levels.",
    "She carefully explained the new policy to every employee.",
    "Our flight was delayed because of heavy snow at the airport.",
    "The committee will review the budget proposal next Tuesday.",
    "Reading widely improves both vocabulary and critical thinking.",
    "He repaired the old bicycle and rode it to the market.",
    "Scientists discovered a new species of frog in the rainforest.",
]
LANGS = ["id", "fr", "de", "es", "ru", "ar", "zh", "ja", "hi"]


# chrF lives in the eval package now (one source of truth); re-export for back-compat.
from transdoc.eval.metrics import chrf  # noqa: E402


def main() -> None:
    engine = Engine(os.environ.get("TRANSDOC_BENCH_ENGINE", "fallback"))
    tr = get_translator(Config(target_lang="en", engine=engine))
    print(f"engine={engine.value}  sentences={len(SENTENCES)}\n")
    print(f"{'lang':5} {'chrF':>6}  back-translation sample")
    print("-" * 70)
    scores = {}
    for lang in LANGS:
        fwd = tr.translate_batch(SENTENCES, Config(target_lang=lang, engine=engine), src="en")
        back = tr.translate_batch(fwd, Config(target_lang="en", engine=engine), src=lang)
        s = sum(chrf(o, b) for o, b in zip(SENTENCES, back)) / len(SENTENCES)
        scores[lang] = s
        print(f"{lang:5} {s:6.1f}  {back[0][:50]!r}")
    avg = sum(scores.values()) / len(scores)
    print("-" * 70)
    print(f"AVERAGE chrF (round-trip): {avg:.1f}")
    print("ranked:", ", ".join(f"{k}={v:.0f}" for k, v in
                               sorted(scores.items(), key=lambda x: -x[1])))


if __name__ == "__main__":
    main()
