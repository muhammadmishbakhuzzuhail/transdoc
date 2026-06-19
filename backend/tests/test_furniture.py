# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Cross-page running header/footer + page-number removal by repetition in the margins."""

from __future__ import annotations

from transdoc.extract.furniture import drop_repeated
from transdoc.ir import BBox, Block, BlockType, Confidence, Document


def _doc(npages=5, h=842.0):
    d = Document(source_path="x", mime="application/pdf", page_count=npages)
    for p in range(npages):
        d.page_sizes[p] = (595.0, h)
    return d


def _b(text, page, y0, y1):
    return Block(id=f"{page}-{y0}", type=BlockType.PARAGRAPH, page=page, text=text,
                 bbox=BBox(x0=40, y0=y0, x1=500, y1=y1), confidence=Confidence())


def test_drops_running_header_and_page_number():
    d = _doc(5)
    for p in range(5):
        d.blocks.append(_b("ACME Confidential Report", p, 10, 24))      # top-margin header
        d.blocks.append(_b(f"Page {p + 1}", p, 815, 832))              # bottom page number
        d.blocks.append(_b(f"Unique body text on page {p}", p, 400, 440))  # body
    removed = drop_repeated(d)
    assert removed == 10                                                # 5 headers + 5 numbers
    assert all("Confidential" not in b.text for b in d.blocks)
    assert all(not b.text.startswith("Page ") for b in d.blocks)
    assert sum(1 for b in d.blocks if "Unique body" in b.text) == 5     # body kept


def test_keeps_non_repeating_margin_text():
    d = _doc(5)
    d.blocks.append(_b("A one-off note at the top of page 0", 0, 10, 24))
    for p in range(5):
        d.blocks.append(_b(f"body {p}", p, 400, 440))
    assert drop_repeated(d) == 0                                        # nothing repeats enough


def test_no_op_on_short_docs():
    d = _doc(2)
    for p in range(2):
        d.blocks.append(_b("Header", p, 10, 24))
    assert drop_repeated(d) == 0                                        # < 3 pages -> skip
