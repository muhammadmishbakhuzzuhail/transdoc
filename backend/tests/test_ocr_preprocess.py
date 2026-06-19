# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""OCR preprocessing: geometry-preserving image cleanup + its use in the AUTO escalation path
as a cheap retry before falling back to the stronger engine."""

from __future__ import annotations

from io import BytesIO

import pytest

PIL = pytest.importorskip("PIL")

from PIL import Image  # noqa: E402

from transdoc.config import Config  # noqa: E402
from transdoc.ir import BBox, Block, BlockType, Confidence  # noqa: E402
from transdoc.ocr.preprocess import _otsu_threshold, enhance  # noqa: E402


def _png(color=128, size=(40, 30)) -> bytes:
    im = Image.new("RGB", size, (color, color, color))
    # a darker patch so there is foreground/background contrast for Otsu
    for x in range(5, 15):
        for y in range(5, 15):
            im.putpixel((x, y), (10, 10, 10))
    out = BytesIO()
    im.save(out, format="PNG")
    return out.getvalue()


def test_otsu_threshold_bimodal():
    hist = [0] * 256
    hist[30] = 100      # dark cluster
    hist[220] = 100     # light cluster
    t = _otsu_threshold(hist)
    # any split in [30, 220) separates the two clusters (p>t puts 30->fg, 220->bg)
    assert 30 <= t < 220


def test_otsu_empty_histogram_safe():
    assert _otsu_threshold([0] * 256) == 127


def test_enhance_preserves_dimensions_and_binarizes():
    raw = _png()
    out = enhance(raw)
    src, dst = Image.open(BytesIO(raw)), Image.open(BytesIO(out))
    assert dst.size == src.size                       # geometry preserved (no rescale/rotate)
    levels = set(dst.convert("L").getdata())
    assert levels <= {0, 255}                         # binarized to black/white only


def test_enhance_unreadable_bytes_returns_original():
    assert enhance(b"not an image") == b"not an image"


# --- AUTO escalation: the cleaned-image retry wins without needing the stronger engine -------

def _blocks(conf, tag):
    return [Block(id=f"{tag}{i}", type=BlockType.PARAGRAPH, page=0, text=f"{tag} line {i}",
                  bbox=BBox(x0=0, y0=i, x1=10, y1=i + 5),
                  confidence=Confidence(source="ocr", ocr=conf)) for i in range(3)]


class _PreprocessAwareTess:
    """Low confidence on the raw image, high confidence once it's been cleaned up."""

    def __init__(self, raw_bytes):
        self._enhanced = enhance(raw_bytes)

    def recognize_image_bytes(self, img, cfg, page=0):
        if img == self._enhanced:
            return _blocks(0.95, "clean")
        return _blocks(0.30, "raw")


def test_preprocess_retry_recovers_low_confidence_page():
    from transdoc.ocr.auto import EscalatingOCR

    raw = _png()
    e = EscalatingOCR()
    e._tess = _PreprocessAwareTess(raw)
    e._strong_tried = True
    e._strong = None                                  # no stronger engine available
    out = e.recognize_image_bytes(raw, Config(target_lang="id"))
    assert out[0].text.startswith("clean")            # the cleaned-image pass won, no escalation
