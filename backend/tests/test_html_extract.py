# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""HTML is parsed as a DOM (tags stripped, structure typed), not translated as literal markup."""

from __future__ import annotations

from transdoc.config import Config
from transdoc.extract.html import extract
from transdoc.ir import BlockType

_HTML = (b"<html><head><title>T</title><style>.x{}</style></head><body>"
         b"<h1>Heading</h1><p>Para with <b>bold</b> word.</p>"
         b"<ul><li>one</li><li>two</li></ul>"
         b"<table><tr><th>A</th></tr><tr><td>1</td></tr></table>"
         b"<script>bad()</script></body></html>")


def test_html_dom_parse(tmp_path):
    f = tmp_path / "d.html"
    f.write_bytes(_HTML)
    d = extract(str(f), Config(target_lang="id"))
    texts = [b.text for b in d.blocks if b.text]
    joined = " ".join(texts)
    assert "Heading" in joined and "Para with bold word." in joined
    assert "one" in joined and "two" in joined
    assert "<" not in joined and "script" not in joined and "bad()" not in joined   # no markup/JS
    assert any(b.type == BlockType.TABLE for b in d.blocks)
    assert any(b.type in (BlockType.TITLE, BlockType.HEADING) for b in d.blocks)
