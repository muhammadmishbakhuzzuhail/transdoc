# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Pipeline cleans intermediate crop temp dirs after rendering (audit: per-run /tmp leak)."""

from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz")

from transdoc.config import Config, Engine, OutputFormat  # noqa: E402
from transdoc.pipeline import run  # noqa: E402


def test_tmp_dirs_removed_after_run(tmp_path):
    d = fitz.open()
    p = d.new_page(width=400, height=400)
    p.insert_text((40, 60), "hello world to translate")
    src = tmp_path / "s.pdf"
    d.save(str(src))
    d.close()
    out = tmp_path / "o.pdf"
    res = run(str(src), Config(target_lang="id", engine=Engine.ECHO,
                               output_format=OutputFormat.PDF), out_path=str(out))
    # any registered temp dirs must be gone + the list cleared
    assert res.doc.tmp_dirs == []


def test_cleanup_unlinks_display_png():
    # an image source's deskew/orient overlay background is a delete=False temp file outside
    # tmp_dirs; _cleanup_tmp must unlink it (audit: per-image /tmp leak).
    import os
    import tempfile

    from transdoc.ir import Document
    from transdoc.pipeline import _cleanup_tmp
    f = tempfile.NamedTemporaryFile(prefix="transdoc_disp_", suffix=".png", delete=False)
    f.write(b"\x89PNG")
    f.close()
    doc = Document(source_path="x", mime="image")
    doc.render_path = f.name
    _cleanup_tmp(doc)
    assert not os.path.exists(f.name)
