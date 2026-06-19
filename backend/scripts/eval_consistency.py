# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Terminology-consistency eval — measure BEFORE building force-consistency (glossary auto-extract).

Sentence MT translates each segment independently, so a term repeated across a document can come
out rendered differently each time — the document-level accuracy lever the audit flagged. But
before adding force-consistency (which can be WRONG if it picks a bad canonical rendering), measure
whether inconsistency is actually a problem.

Method: for each source term, translate it in isolation (the canonical rendering) and in several
carrier sentences; report the fraction of carriers whose translation CONTAINS the canonical
rendering. 1.0 = the engine already renders the term consistently (force-consistency would add
little); low = the term drifts across contexts (force-consistency could help — at the risk noted).
Common nouns may score below 1.0 from legitimate inflection, so weigh proper nouns/terms highest.

Online (the engine is online). Local/opt-in.

    cd backend && .venv/bin/python -m scripts.eval_consistency            # default langs+terms
    cd backend && .venv/bin/python -m scripts.eval_consistency fr de id
"""

from __future__ import annotations

import sys

TERMS = ["dashboard", "shipment", "invoice", "subscription", "Transdoc", "API"]
CARRIERS = [
    "The {t} is ready now.",
    "Please review the {t} carefully.",
    "Our {t} was updated yesterday.",
    "Every {t} must be checked.",
    "I will send the {t} tomorrow.",
]
LANGS = ["fr", "de", "es", "id"]


def consistency(term: str, carriers: list[str], translate_fn) -> float:
    """Fraction of carrier translations that contain the term's canonical (isolated) rendering."""
    canon = (translate_fn(term) or "").strip().lower()
    if not canon:
        return 1.0
    hits = sum(1 for c in carriers if canon in (translate_fn(c.format(t=term)) or "").lower())
    return hits / len(carriers)


def _engine_fn(gcode: str):
    from transdoc.config import Config, Engine
    from transdoc.translate import get_translator
    cfg = Config(target_lang=gcode, source_lang="en", engine=Engine.GOOGLE)
    tr = get_translator(cfg)
    return lambda text: tr.translate_batch([text], cfg, src="en")[0]


def main(argv: list[str]) -> int:
    langs = argv or LANGS
    print("Terminology consistency (1.0 = canonical rendering reused in every context)\n")
    print(f"{'lang':6} " + " ".join(f"{t[:9]:>9}" for t in TERMS) + f"{'mean':>7}")
    print("-" * (7 + 10 * len(TERMS) + 7))
    grand: list[float] = []
    for g in langs:
        try:
            fn = _engine_fn(g)
            scores = [consistency(t, CARRIERS, fn) for t in TERMS]
        except Exception as e:
            print(f"{g:6} ERROR {type(e).__name__}: {e}")
            continue
        grand.extend(scores)
        row = " ".join(f"{s:>9.2f}" for s in scores)
        print(f"{g:6} {row}{sum(scores) / len(scores):>7.2f}")
    if grand:
        print("-" * (7 + 10 * len(TERMS) + 7))
        print(f"{'ALL':6} " + " " * (10 * len(TERMS)) + f"{sum(grand) / len(grand):>7.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
