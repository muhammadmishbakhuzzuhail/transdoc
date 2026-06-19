# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Reading-order regression: the default XY-cut + FLOW reorder must keep the hard two-column arXiv
pages in perfect reading order. This is the committed baseline that closes the 'no reading-order
eval' gap and is the number any alternative ordering engine (e.g. Surya) has to beat — measured at
tau 1.0, so XY-cut is kept as the default.

Uses layout='off' (heuristic) for a fast, deterministic extraction; skips when the corpus PDF or
its hand-authored .order.json reference isn't present."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_DOCS = ["arxiv_bert_en", "arxiv_attention_en"]
_DIR = Path("corpus/real/digital_text")


@pytest.mark.parametrize("stem", _DOCS)
def test_xycut_reading_order_is_optimal(stem):
    pdf = _DIR / f"{stem}.pdf"
    ref = _DIR / f"{stem}.order.json"
    if not pdf.exists() or not ref.exists():
        pytest.skip("corpus pdf / order ref not present")

    from transdoc.config import Config
    from transdoc.eval.metrics import reading_order_match
    from transdoc.extract import extract
    from transdoc.extract.base import reorder_vertical_last
    from transdoc.ingest.detect import detect

    doc = extract(detect(str(pdf)), Config(target_lang="id", layout="off"))
    reorder_vertical_last(doc)                       # the FLOW pipeline step
    hyps = [(b.bbox.x0, b.bbox.y0, b.bbox.x1, b.bbox.y1)
            for b in doc.ordered_blocks() if b.page == 0 and b.bbox]
    refs = [tuple(e["bbox"]) for e in json.loads(ref.read_text())]
    m = reading_order_match(refs, hyps)
    assert m["kendall_tau"] >= 0.99, (stem, m)
    assert m["coverage"] >= 0.99, (stem, m)
