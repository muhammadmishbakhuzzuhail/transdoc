"""Page selection (--pages) limits extraction so only requested pages are translated."""

from __future__ import annotations

import fitz

from transdoc.config import Config
from transdoc.extract.pdf import _parse_pages, extract


def test_parse_pages_forms():
    assert sorted(_parse_pages("1-3", 15)) == [0, 1, 2]
    assert sorted(_parse_pages("1,5,10", 15)) == [0, 4, 9]
    assert sorted(_parse_pages("13-", 15)) == [12, 13, 14]   # open-ended
    assert sorted(_parse_pages("-2", 15)) == [0, 1]          # open start
    assert _parse_pages(None, 15) is None                    # all
    assert _parse_pages("", 15) is None
    assert _parse_pages("20", 15) is None                    # out of range -> none


def _pdf(tmp_path):
    src = tmp_path / "s.pdf"
    d = fitz.open()
    for i in range(5):
        d.new_page().insert_text((40, 60), f"Page {i} body text here.", fontsize=12)
    d.save(str(src))
    d.close()
    return str(src)


def test_extraction_limited_to_selected_pages(tmp_path):
    src = _pdf(tmp_path)
    allb = extract(src, Config(target_lang="id"))
    assert sorted(set(b.page for b in allb.blocks)) == [0, 1, 2, 3, 4]
    sel = extract(src, Config(target_lang="id", pages="2-3"))
    assert sorted(set(b.page for b in sel.blocks)) == [1, 2]


def test_parse_pages_skips_malformed_no_crash():
    from transdoc.extract.pdf import _parse_pages
    # malformed parts must be skipped, not crash (audit P1: ValueError on "a-5")
    assert _parse_pages("a-5", 10) is None              # only bad part -> nothing selected
    assert _parse_pages("2,x,4-6", 10) == {1, 3, 4, 5}  # good parts kept, bad skipped
    assert _parse_pages("3-7,10", 10) == {2, 3, 4, 5, 6, 9}   # still works
