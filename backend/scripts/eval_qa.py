# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Translation QA-rate eval: how often does the rule-based QA suite fire on real translations?

Runs curated sentences (entity-dense + length-varied) through the FULL translate path with a real
engine, then applies the rule checks (qa.check_pair) and reports findings by check + severity per
target language. A healthy engine should produce ~0 HARD findings (entities preserved, nothing
untranslated/empty); SOFT findings (length) are informational. Tracks translation health over time
alongside the other eval-* targets.

Online (the engine is online). Local/opt-in.

    cd backend && .venv/bin/python -m scripts.eval_qa                 # default langs, google
    cd backend && .venv/bin/python -m scripts.eval_qa --show fr ar ja
    cd backend && .venv/bin/python -m scripts.eval_qa --engine echo   # smoke (echo flags all)
"""

from __future__ import annotations

import sys
from collections import Counter

from transdoc.config import Config, Engine
from transdoc.ir import Block, BlockType, Confidence, Document
from transdoc.translate import get_translator, translate_document
from transdoc.translate.qa import check_pair

_SENTENCES = [
    "Wire the balance of $1,299.99 to account 4471-8820-1193 before 03/15/2026.",
    "Email support@example.com or visit https://example.com/help for the full details today.",
    "Flight AA-2476 departs at 14:05 from gate B12 with 250 passengers aboard.",
    "The patient received 250 mg of the drug at 08:30 on 2026-01-07 in ward 3.",
    "Refer to ISO 9001:2015 and RFC 2616 in the appendix for the complete specification.",
    "Coordinates are 40.7128, -74.0060 at an elevation of 10.5 metres above sea level.",
]
LANGS = ["fr", "de", "es", "ru", "ar", "hi", "zh-CN", "ja", "ko", "id"]


def _run_lang(lang: str, engine: Engine, show: bool) -> Counter:
    cfg = Config(target_lang=lang, source_lang="en", engine=engine)
    doc = Document(source_path="x.txt", mime="text/plain")
    doc.source_lang = "en"
    doc.blocks = [Block(id=f"s{i}", type=BlockType.PARAGRAPH, page=0, text=s,
                        confidence=Confidence(source="digital")) for i, s in enumerate(_SENTENCES)]
    translate_document(doc, get_translator(cfg), cfg)
    counts: Counter = Counter()
    for b in doc.blocks:
        for f in check_pair(b.id, b.text, b.translated, cfg):
            counts[(f.severity, f.check)] += 1
            if show and f.severity == "hard":
                print(f"   [{lang}] {f.check}: {f.detail}\n      src: {b.text[:80]}\n"
                      f"      mt : {(b.translated or '')[:80]}")
    return counts


def main(argv: list[str]) -> int:
    show = "--show" in argv
    argv = [a for a in argv if a != "--show"]
    engine = Engine.GOOGLE
    if "--engine" in argv:
        i = argv.index("--engine")
        engine = Engine(argv[i + 1])
        del argv[i:i + 2]
    langs = argv or LANGS

    print(f"QA eval — engine={engine.value}, {len(_SENTENCES)} sentences/lang")
    print(f"{'lang':6} {'hard':>5} {'soft':>5}   {'by check'}")
    print("-" * 60)
    grand: Counter = Counter()
    for lang in langs:
        try:
            c = _run_lang(lang, engine, show)
        except Exception as e:
            print(f"{lang:6} {'ERR':>5}  {e}")
            continue
        grand.update(c)
        hard = sum(n for (sev, _), n in c.items() if sev == "hard")
        soft = sum(n for (sev, _), n in c.items() if sev == "soft")
        by = ", ".join(f"{chk}={n}" for (_, chk), n in sorted(c.items())) or "clean"
        print(f"{lang:6} {hard:>5} {soft:>5}   {by}")
    print("-" * 60)
    total_hard = sum(n for (sev, _), n in grand.items() if sev == "hard")
    print(f"TOTAL hard findings: {total_hard} (lower is better; 0 = entities all preserved)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
