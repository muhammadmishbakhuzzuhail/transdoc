"""Running header/footer stripping: repeated top/bottom-band blocks are dropped for FLOW
output, but the detector leaves unique body text and short documents alone."""

from __future__ import annotations

from transdoc.headers import strip_running_headers
from transdoc.ir import BBox, Block, BlockType, Confidence, Document


def _doc(npages: int) -> Document:
    d = Document(source_path="x.pdf", mime="application/pdf", page_count=npages)
    d.page_sizes = {p: (400.0, 500.0) for p in range(npages)}
    blocks = []
    for p in range(npages):
        blocks.append(Block(id=f"h{p}", type=BlockType.PARAGRAPH, page=p,
                            text="ACME Confidential Report", bbox=BBox(x0=40, y0=15, x1=300, y1=28),
                            confidence=Confidence(source="digital")))
        blocks.append(Block(id=f"b{p}", type=BlockType.PARAGRAPH, page=p,
                            text=f"Unique body paragraph {p}", bbox=BBox(x0=40, y0=250, x1=360, y1=270),
                            confidence=Confidence(source="digital")))
    d.blocks = blocks
    return d


def test_strips_repeating_header():
    d = _doc(4)
    removed = strip_running_headers(d)
    assert removed == 4
    assert not [b for b in d.blocks if "ACME" in b.text]
    assert len([b for b in d.blocks if "Unique body" in b.text]) == 4   # body untouched


def test_short_doc_untouched():
    d = _doc(2)                       # < 3 pages -> can't distinguish a running header
    assert strip_running_headers(d) == 0
    assert len(d.blocks) == 4
