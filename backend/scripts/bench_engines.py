# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Side-by-side engine benchmark: round-trip back-translation chrF for two engines on the same
sentences, so the NLLB-vs-Google default decision is made on numbers, not assumptions.

EN -> lang -> EN through each engine; chrF(original, back) — higher = meaning/wording survived.
LIVE NETWORK for google; NLLB is offline. Run manually, never in CI.

    .venv/bin/python scripts/bench_engines.py
    BENCH_LANGS=id,ar,zh BENCH_ENGINES=google,nllb .venv/bin/python scripts/bench_engines.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from transdoc.config import Config, Engine  # noqa: E402
from transdoc.eval.metrics import chrf  # noqa: E402
from transdoc.translate import get_translator  # noqa: E402

SENTENCES = [
    "The quick brown fox jumps over the lazy dog near the river.",
    "Climate change threatens coastal cities with rising sea levels.",
    "She carefully explained the new policy to every employee.",
    "Our flight was delayed because of heavy snow at the airport.",
    "The committee will review the proposal at next week's meeting.",
]
LANGS = os.environ.get("BENCH_LANGS", "id,ar,zh,ru,de").split(",")
ENGINES = os.environ.get("BENCH_ENGINES", "google,nllb").split(",")


def round_trip(engine: str, lang: str) -> tuple[float, float, str]:
    tr = get_translator(Config(target_lang=lang, engine=Engine(engine)))
    t0 = time.monotonic()
    fwd = tr.translate_batch(SENTENCES, Config(target_lang=lang, engine=Engine(engine)), src="en")
    back = tr.translate_batch(fwd, Config(target_lang="en", engine=Engine(engine)), src=lang)
    dt = time.monotonic() - t0
    score = sum(chrf(o, b) for o, b in zip(SENTENCES, back)) / len(SENTENCES)
    return score, dt, back[0][:48]


def main() -> None:
    print(f"sentences={len(SENTENCES)}  langs={LANGS}  engines={ENGINES}\n")
    print(f"{'lang':5}", *(f"{e:>22}" for e in ENGINES))
    print("-" * (5 + 24 * len(ENGINES)))
    totals = {e: [] for e in ENGINES}
    for lang in LANGS:
        cells = []
        for e in ENGINES:
            try:
                s, dt, _ = round_trip(e, lang)
                totals[e].append(s)
                cells.append(f"chrF {s:5.1f} ({dt:4.1f}s)")
            except Exception as ex:
                cells.append(f"ERR {type(ex).__name__}")
        print(f"{lang:5}", *(f"{c:>22}" for c in cells))
    print("-" * (5 + 24 * len(ENGINES)))
    print(f"{'AVG':5}", *(f"{(sum(v)/len(v) if v else 0):>21.1f} " for v in totals.values()))


if __name__ == "__main__":
    main()
