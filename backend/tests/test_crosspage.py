"""Cross-page paragraph continuation (Area D, D3), flow output only. A paragraph split by a page
break is rejoined before translation; complete sentences and structural blocks are left alone."""

from __future__ import annotations

from transdoc.extract.crosspage import merge_cross_page
from transdoc.ir import BBox, Block, BlockType, Document


def _b(bid, text, page, t=BlockType.PARAGRAPH, y0=400.0):
    return Block(id=bid, type=t, page=page, text=text,
                 bbox=BBox(x0=40, y0=y0, x1=560, y1=y0 + 40))


def _doc(blocks, pages=2):
    d = Document(source_path="x", mime="application/pdf", page_count=pages)
    for p in range(pages):
        d.page_sizes[p] = (600.0, 800.0)
    d.blocks = blocks
    return d


def test_open_clause_merges_across_pages():
    d = _doc([
        _b("a", "The committee reviewed the proposal and decided that", 0, y0=700),
        _b("b", "the budget should be increased next year.", 1, y0=60),
    ])
    n = merge_cross_page(d)
    assert n == 1
    assert len(d.blocks) == 1
    assert d.blocks[0].text == (
        "The committee reviewed the proposal and decided that "
        "the budget should be increased next year.")


def test_hyphen_split_is_dehyphenated():
    d = _doc([
        _b("a", "This requires inter-", 0, y0=700),
        _b("b", "national cooperation.", 1, y0=60),
    ])
    merge_cross_page(d)
    assert d.blocks[0].text == "This requires international cooperation."


def test_completed_sentence_not_merged():
    d = _doc([
        _b("a", "The section ends here.", 0, y0=700),
        _b("b", "A new paragraph begins on the next page.", 1, y0=60),
    ])
    assert merge_cross_page(d) == 0
    assert len(d.blocks) == 2


def test_heading_head_not_merged():
    d = _doc([
        _b("a", "trailing clause with no terminator", 0, y0=700),
        _b("b", "New Chapter", 1, t=BlockType.HEADING, y0=60),
    ])
    assert merge_cross_page(d) == 0


def test_uppercase_head_not_merged():
    # tail open but next page starts a capitalised new sentence -> likely a fresh paragraph
    d = _doc([
        _b("a", "the report continues with several points", 0, y0=700),
        _b("b", "Furthermore the data shows growth.", 1, y0=60),
    ])
    assert merge_cross_page(d) == 0


def test_non_adjacent_pages_not_merged():
    d = _doc([
        _b("a", "an open clause that would continue", 0, y0=700),
        _b("b", "and here is more text", 2, y0=60),
    ], pages=3)
    assert merge_cross_page(d) == 0


# --- intra-page merge (same-page mis-segmented paragraph) -----------------------------------

from transdoc.extract.crosspage import merge_intra_page  # noqa: E402


def test_intra_page_merges_same_column_open_clause():
    d = _doc([
        _b("a", "The committee reviewed the proposal and decided that", 0, y0=200),
        _b("b", "the budget should increase next year.", 0, y0=240),
    ], pages=1)
    n = merge_intra_page(d)
    assert n == 1 and len(d.blocks) == 1
    assert d.blocks[0].text == (
        "The committee reviewed the proposal and decided that "
        "the budget should increase next year.")


def test_intra_page_skips_different_column():
    left = Block(id="L", type=BlockType.PARAGRAPH, page=0, text="an open clause that continues",
                 bbox=BBox(x0=40, y0=200, x1=280, y1=240))
    right = Block(id="R", type=BlockType.PARAGRAPH, page=0, text="and more text here",
                  bbox=BBox(x0=320, y0=200, x1=560, y1=240))
    d = _doc([left, right], pages=1)
    assert merge_intra_page(d) == 0
    assert len(d.blocks) == 2


def test_intra_page_completed_sentence_not_merged():
    d = _doc([
        _b("a", "This section is complete.", 0, y0=200),
        _b("b", "A separate new paragraph here.", 0, y0=240),
    ], pages=1)
    assert merge_intra_page(d) == 0


def test_intra_page_chains_three_blocks():
    d = _doc([
        _b("a", "first part that runs on", 0, y0=200),
        _b("b", "into a second part and then", 0, y0=230),
        _b("c", "a final clause to close.", 0, y0=260),
    ], pages=1)
    n = merge_intra_page(d)
    assert n == 2 and len(d.blocks) == 1
