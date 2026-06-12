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


def _char_ngrams(s: str, n: int) -> list[str]:
    s = s.lower()
    return [s[i:i + n] for i in range(len(s) - n + 1)] if len(s) >= n else []


def chrf(ref: str, hyp: str, max_n: int = 6, beta: float = 2.0) -> float:
    """chrF: average char n-gram (1..max_n) F-score, recall-weighted (beta=2)."""
    from collections import Counter
    fs = []
    for n in range(1, max_n + 1):
        r, h = Counter(_char_ngrams(ref, n)), Counter(_char_ngrams(hyp, n))
        if not r or not h:
            continue
        match = sum((r & h).values())
        prec = match / sum(h.values())
        rec = match / sum(r.values())
        if prec + rec == 0:
            fs.append(0.0)
            continue
        fs.append((1 + beta ** 2) * prec * rec / (beta ** 2 * prec + rec))
    return 100 * sum(fs) / len(fs) if fs else 0.0


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
