# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Entity-preservation eval: do numbers, URLs, emails, dates, codes, and prices survive
translation verbatim?

For a *document* translator this is the accuracy that matters and FLORES can't measure: a single
corrupted account number, URL, or price is a worse failure than an awkward sentence. The pipeline
protects these tokens with placeholders before translation and restores them after — but the MT
engine can mangle a placeholder (translate it, space it, reorder digits), silently losing the
token. This runs curated sentences through the FULL translate path and checks each known token
appears verbatim in the output, per target language (Latin / RTL / CJK stress the placeholder).

Online (the engine is online). Local/opt-in.

    cd backend && .venv/bin/python -m scripts.eval_preserve            # default langs
    cd backend && .venv/bin/python -m scripts.eval_preserve --show fr ar ja
"""

from __future__ import annotations

import os
import sys

# Each case: a sentence + the tokens that MUST survive verbatim. Mix of the protected categories.
_CASES = [
    ("Wire the balance to account 4471-8820-1193 before 03/15/2026.",
     ["4471-8820-1193", "03/15/2026"]),
    ("Email support@example.com or visit https://example.com/help for details.",
     ["support@example.com", "https://example.com/help"]),
    ("The invoice total is $1,299.99 plus 7.5% tax.",
     ["$1,299.99", "7.5%"]),
    ("Flight AA-2476 departs at 14:05 from gate B12.",
     ["AA-2476", "14:05", "B12"]),
    ("Refer to ISO 9001:2015 and RFC 2616 in the appendix.",
     ["ISO 9001:2015", "RFC 2616"]),
    ("The patient received 250 mg of the drug at 08:30 on 2026-01-07.",
     ["250", "08:30", "2026-01-07"]),
    ("Order #A1B2C3 shipped via tracking 1Z999AA10123456784.",
     ["#A1B2C3", "1Z999AA10123456784"]),
    ("Coordinates: 40.7128, -74.0060; elevation 10.5 m.",
     ["40.7128", "-74.0060", "10.5"]),
    ("Pay $5 and $10 now, or $1,299.99 vs $50 each.",
     ["$5", "$10", "$1,299.99", "$50"]),
    ("Upgrade to v2.0.1, ratio 10-20, constant 1.5e-10, follow @alice.",
     ["v2.0.1", "10-20", "1.5e-10", "@alice"]),
]

LANGS = ["fr", "de", "es", "ru", "ar", "hi", "zh-CN", "ja", "ko"]


def _check(doc, tokens_by_block: list[list[str]]) -> tuple[int, int, list[str]]:
    kept = total = 0
    misses: list[str] = []
    for b, tokens in zip(doc.blocks, tokens_by_block):
        out = b.output_text
        for tok in tokens:
            total += 1
            if tok in out:
                kept += 1
            else:
                misses.append(tok)
    return kept, total, misses


def run_lang(gcode: str, engine: str, show: bool) -> float:
    from transdoc.config import Config, Engine
    from transdoc.ir import Block, BlockType, Document
    from transdoc.translate import get_translator, translate_document

    doc = Document(source_path="x.txt", mime="text")
    doc.blocks = [Block(id=f"b{i}", type=BlockType.PARAGRAPH, text=t)
                  for i, (t, _) in enumerate(_CASES)]
    cfg = Config(target_lang=gcode, source_lang="en", engine=Engine(engine))
    translate_document(doc, get_translator(cfg), cfg)
    kept, total, misses = _check(doc, [toks for _, toks in _CASES])
    if show:
        for b in doc.blocks:
            print(f"   {b.output_text[:120]}")
        if misses:
            print(f"   LOST: {', '.join(misses)}")
    return 100.0 * kept / total if total else 0.0


def main(argv: list[str]) -> int:
    engine = "google"
    show = False
    args = list(argv)
    if "--engine" in args:
        i = args.index("--engine")
        engine = args[i + 1]
        args = args[:i] + args[i + 2:]
    if "--show" in args:
        show = True
        args.remove("--show")
    langs = args or LANGS

    # fresh measurement — don't let the cross-run cache mask a placeholder regression
    os.environ.setdefault("TRANSDOC_TM_DISABLE", "1")

    print(f"Entity preservation through translation (engine={engine})\n")
    print(f"{'lang':8} {'kept %':>7}")
    print("-" * 18)
    scores = []
    for g in langs:
        try:
            s = run_lang(g, engine, show)
        except Exception as e:
            print(f"{g:8} ERROR {type(e).__name__}: {e}")
            continue
        scores.append(s)
        print(f"{g:8} {s:>7.1f}")
    if scores:
        print("-" * 18)
        print(f"{'mean':8} {sum(scores) / len(scores):>7.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
