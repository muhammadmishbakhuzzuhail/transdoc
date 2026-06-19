# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Block-typing enrichment (Area D, D2): running header/footer + page-number detection by margin
band + cross-page repetition, and the typing_match eval metric."""

from __future__ import annotations

from transdoc.eval.metrics import typing_match
from transdoc.extract.block_types import detect_marginalia, detect_running_heads
from transdoc.ir import NON_TRANSLATABLE, BBox, Block, BlockType, Document


def _b(bid, text, x0, y0, x1, y1, page, t=BlockType.PARAGRAPH):
    return Block(id=bid, type=t, page=page, text=text, bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1))


def _doc(pages=3):
    d = Document(source_path="x", mime="application/pdf", page_count=pages)
    for p in range(pages):
        d.page_sizes[p] = (600.0, 800.0)
    return d


def test_repeated_margin_text_becomes_header_and_footer():
    d = _doc(3)
    for p in range(3):
        d.blocks.append(_b(f"h{p}", "Annual Report 2026", 40, 20, 560, 40, p))     # top, repeats
        d.blocks.append(_b(f"body{p}", "Body text on the page.", 40, 300, 560, 360, p))
        d.blocks.append(_b(f"f{p}", "Confidential", 40, 770, 560, 790, p))         # bottom, repeats
    detect_running_heads(d)
    assert all(b.type == BlockType.HEADER for b in d.blocks if b.id.startswith("h"))
    assert all(b.type == BlockType.FOOTER for b in d.blocks if b.id.startswith("f"))
    assert all(b.type == BlockType.PARAGRAPH for b in d.blocks if b.id.startswith("body"))


def test_numeric_margin_cell_becomes_page_number():
    d = _doc(3)
    for p in range(3):
        d.blocks.append(_b(f"pn{p}", str(p + 1), 290, 772, 310, 790, p))   # changing number
        d.blocks.append(_b(f"body{p}", "Body.", 40, 300, 560, 360, p))
    detect_running_heads(d)
    assert all(b.type == BlockType.PAGE_NUMBER for b in d.blocks if b.id.startswith("pn"))


def test_title_high_on_page_not_tagged_header():
    # a one-off title near the top must stay TITLE (appears once -> no repetition)
    d = _doc(1)
    d.blocks.append(_b("t", "My Unique Document Title", 40, 20, 560, 50, 0, t=BlockType.TITLE))
    detect_running_heads(d)
    assert d.blocks[0].type == BlockType.TITLE


def test_does_not_clobber_specific_types():
    d = _doc(2)
    for p in range(2):
        d.blocks.append(_b(f"c{p}", "Figure 1: chart", 40, 22, 560, 40, p, t=BlockType.CAPTION))
    detect_running_heads(d)
    assert all(b.type == BlockType.CAPTION for b in d.blocks)   # caption survives margin+repeat


def _box(bid, x0, y0, x1, y1, page=0, t=BlockType.PARAGRAPH):
    return Block(id=bid, type=t, page=page, text="x",
                 bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1))


def test_narrow_outer_margin_note_beside_body_becomes_aside():
    d = _doc(1)                                            # page 600x800
    body = _box("body", 40, 300, 500, 360)                # wide body (~77%)
    note = _box("note", 520, 300, 585, 360)               # narrow note in right outer margin
    d.blocks = [body, note]
    detect_marginalia(d)
    assert note.type == BlockType.ASIDE
    assert body.type == BlockType.PARAGRAPH


def test_column_not_mistaken_for_marginalia():
    d = _doc(1)
    # two ~42%-wide columns: neither is narrow enough (>20%) to be marginalia
    left = _box("L", 40, 300, 290, 360)
    right = _box("R", 310, 300, 560, 360)
    d.blocks = [left, right]
    detect_marginalia(d)
    assert all(b.type == BlockType.PARAGRAPH for b in d.blocks)


def test_aside_is_translatable():
    assert BlockType.ASIDE not in NON_TRANSLATABLE


def test_typing_metric_accuracy_and_confusion():
    refs = [("header", (0, 0, 100, 20)), ("paragraph", (0, 40, 100, 80)),
            ("footer", (0, 90, 100, 100))]
    hyps = [("header", (0, 0, 100, 20)), ("paragraph", (0, 40, 100, 80)),
            ("paragraph", (0, 90, 100, 100))]            # footer mis-typed as paragraph
    m = typing_match(refs, hyps)
    assert m["matched"] == 3
    assert abs(m["accuracy"] - 2 / 3) < 1e-9
    assert ("footer", "paragraph") in m["confusion"]
    assert m["per_type"]["footer"]["recall"] == 0.0
