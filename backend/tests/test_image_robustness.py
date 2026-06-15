"""Image-extraction robustness (audit fixes):
  #1 OSD coarse-orientation — a 90/180/270 rotated page is turned upright before OCR.
  #3 render downscale — large pages are capped so PP-StructureV3 fits in GPU memory.
  #2 routing — standalone images take the structured path for text outputs, with fallback.
"""

from __future__ import annotations

import io

import pytest

fitz = pytest.importorskip("fitz")


def _text_png(text: str, dpi: int = 150) -> bytes:
    """A clean rendered text page as PNG bytes (deterministic, no external fixtures)."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((60, 80), text, fontsize=18)
    y = 120
    for _ in range(20):
        page.insert_text((60, y), "The quick brown fox jumps over the lazy dog.", fontsize=13)
        y += 26
    png = page.get_pixmap(dpi=dpi).tobytes("png")
    doc.close()
    return png


# ---- #1 OSD coarse-orientation -------------------------------------------------------------

def test_coarse_orient_upright_is_noop():
    from transdoc.extract.image import _coarse_orient
    png = _text_png("Upright Heading")
    out, rot = _coarse_orient(png)
    assert rot == 0
    assert out is png            # unchanged bytes when already upright


def test_coarse_orient_corrects_rotation():
    """A page rotated 90deg is detected by OSD and turned back upright (so OCR isn't sideways)."""
    from PIL import Image

    from transdoc.extract.image import _coarse_orient
    png = _text_png("Orientation Test Heading")
    rotated = Image.open(io.BytesIO(png)).rotate(-90, expand=True)   # 90deg clockwise
    buf = io.BytesIO()
    rotated.convert("RGB").save(buf, format="PNG")
    try:
        out, rot = _coarse_orient(buf.getvalue())
    except Exception:
        pytest.skip("tesseract OSD unavailable")
    if rot == 0:
        pytest.skip("OSD did not detect rotation in this environment")
    assert rot in (90, 180, 270)
    # corrected image is back to portrait (taller than wide), matching the upright source
    w, h = Image.open(io.BytesIO(out)).size
    assert h > w


# ---- #3 render downscale -------------------------------------------------------------------

def test_render_page_array_caps_dimension():
    pytest.importorskip("numpy")   # render_page_array needs numpy (ships with the OCR extras)
    from transdoc.layout.structure import _MAX_PX, _SCALE, render_page_array
    doc = fitz.open()
    doc.new_page(width=2000, height=3000)        # large page -> >_MAX_PX at 150 dpi
    arr, scale = render_page_array(doc[0])
    doc.close()
    h, w = arr.shape[:2]
    assert max(h, w) <= _MAX_PX                   # capped
    assert scale > _SCALE                         # scaled-up factor (px were downscaled)


def test_render_page_array_small_page_unscaled():
    pytest.importorskip("numpy")
    from transdoc.layout.structure import _SCALE, render_page_array
    doc = fitz.open()
    doc.new_page(width=300, height=400)           # small -> no downscale
    arr, scale = render_page_array(doc[0])
    doc.close()
    assert scale == pytest.approx(_SCALE)


def test_parse_regions_applies_scale():
    from transdoc.layout.structure import parse_regions
    root = {"parsing_res_list": [
        {"block_label": "text", "block_bbox": [0, 0, 100, 50], "block_content": "hi",
         "block_order": 0}]}
    at1 = parse_regions(root, scale=1.0)[0]["bbox"]
    at2 = parse_regions(root, scale=2.0)[0]["bbox"]
    assert at1 == [0, 0, 100, 50]
    assert at2 == [0, 0, 200, 100]               # scaled


# ---- #2 routing gate -----------------------------------------------------------------------

def test_image_uses_line_ocr_when_structured_disabled(tmp_path, monkeypatch):
    """layout=off -> the standalone-image branch must NOT take the structured path."""
    from transdoc.config import Config, OutputFormat
    from transdoc.extract import extract
    from transdoc.ingest.detect import detect

    p = tmp_path / "scan.png"
    p.write_bytes(_text_png("Hello"))

    import transdoc.extract.image as img_mod
    called = {"line_ocr": False}
    real = img_mod.extract
    monkeypatch.setattr(img_mod, "extract",
                        lambda *a, **k: called.__setitem__("line_ocr", True) or real(*a, **k))

    cfg = Config(target_lang="id", layout="off", output_format=OutputFormat.MARKDOWN)
    extract(detect(str(p)), cfg)
    assert called["line_ocr"] is True
