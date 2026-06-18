"""Surya reading-order re-ranking. The Surya VLM is heavy/optional, so these tests exercise the
pure re-rank logic (_reorder_page) with hand-built boxes and the no-op guards (wrong engine,
non-PDF, predictor unavailable)."""

from __future__ import annotations

from transdoc.config import Config
from transdoc.ir import BBox, Block, BlockType, Document
from transdoc.extract import surya_order


def _b(bid, ro, box):
    return Block(id=bid, type=BlockType.PARAGRAPH, reading_order=ro,
                 bbox=BBox(x0=box[0], y0=box[1], x1=box[2], y1=box[3]))


def test_reorder_follows_surya_positions():
    # three blocks the extractor ordered a,b,c; Surya says the reading order is c,a,b.
    a = _b("a", 0, (0, 0, 10, 10))
    b = _b("b", 1, (0, 20, 10, 30))
    c = _b("c", 2, (0, 40, 10, 50))
    boxes = [(0, 40, 10, 50), (0, 0, 10, 10), (0, 20, 10, 30)]   # c, a, b (in points)
    moved = surya_order._reorder_page([a, b, c], boxes)
    assert moved == 1
    assert (c.reading_order, a.reading_order, b.reading_order) == (0, 1, 2)


def test_already_in_order_is_noop():
    a = _b("a", 0, (0, 0, 10, 10))
    b = _b("b", 1, (0, 20, 10, 30))
    boxes = [(0, 0, 10, 10), (0, 20, 10, 30)]                     # same order
    assert surya_order._reorder_page([a, b], boxes) == 0
    assert (a.reading_order, b.reading_order) == (0, 1)


def test_unmatched_block_sorts_last_keeping_order():
    a = _b("a", 0, (0, 0, 10, 10))
    b = _b("b", 1, (0, 20, 10, 30))           # no Surya box overlaps b -> stays after matched
    boxes = [(0, 0, 10, 10)]                   # only matches a
    surya_order._reorder_page([a, b], boxes)
    assert a.reading_order < b.reading_order


def test_empty_boxes_noop():
    a = _b("a", 0, (0, 0, 10, 10))
    assert surya_order._reorder_page([a], []) == 0


def test_disabled_by_default():
    d = Document(source_path="x.pdf", mime="application/pdf")
    d.blocks = [_b("a", 0, (0, 0, 10, 10))]
    assert surya_order.surya_reading_order(d, Config(source_lang="en", target_lang="id")) == 0


def test_non_pdf_skipped(monkeypatch):
    monkeypatch.setattr(surya_order.SuryaOrderer, "_load", lambda self: object())
    d = Document(source_path="x.txt", mime="text/plain")
    d.blocks = [_b("a", 0, (0, 0, 10, 10))]
    cfg = Config(source_lang="en", target_lang="id", reading_order_engine="surya")
    assert surya_order.surya_reading_order(d, cfg) == 0


def test_predictor_unavailable_noop(monkeypatch):
    monkeypatch.setattr(surya_order.SuryaOrderer, "_load", lambda self: None)
    d = Document(source_path="x.pdf", mime="application/pdf")
    d.blocks = [_b("a", 0, (0, 0, 10, 10))]
    cfg = Config(source_lang="en", target_lang="id", reading_order_engine="surya")
    assert surya_order.surya_reading_order(d, cfg) == 0
