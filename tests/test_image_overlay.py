"""Image-overlay output: photo/image source keeps the original image and overlays the
translation at the OCR bbox (Google-Lens-style), instead of flattening to a flow page."""

from __future__ import annotations

import fitz
from PIL import Image

from transdoc.config import Config, Engine, Fidelity, OutputFormat
from transdoc.ir import BBox, Block, BlockType, Confidence, Document, Style
from transdoc.regenerate import regenerate
from transdoc.regenerate.pdf_out import render_image_overlay


def _make_png(path: str, w: int = 400, h: int = 120) -> None:
    Image.new("RGB", (w, h), (220, 220, 220)).save(path)


def _image_doc(src: str) -> Document:
    doc = Document(source_path=src, mime="image", page_count=1)
    doc.blocks = [Block(id="p0-ocr0", type=BlockType.PARAGRAPH, page=0,
                        text="hello world", translated="halo dunia",
                        bbox=BBox(x0=20, y0=30, x1=300, y1=70),
                        style=Style(), confidence=Confidence(source="ocr"))]
    return doc


def test_image_overlay_keeps_image_and_overlays_text(tmp_path):
    src = tmp_path / "photo.png"
    _make_png(str(src))
    out = tmp_path / "photo.id.pdf"
    render_image_overlay(_image_doc(str(src)), Config(target_lang="id"), str(out))

    pdf = fitz.open(str(out))
    assert pdf.page_count == 1
    page = pdf[0]
    assert "halo dunia" in page.get_text()           # translation overlaid
    assert len(page.get_images()) >= 1               # original image kept as background


def test_regenerate_routes_image_to_overlay(tmp_path):
    src = tmp_path / "photo.png"
    _make_png(str(src))
    out = tmp_path / "out.pdf"
    # Lens-style image overlay is now opt-in via -f layout (AUTO reflows).
    cfg = Config(target_lang="id", engine=Engine.ECHO,
                 output_format=OutputFormat.PDF, fidelity=Fidelity.LAYOUT)
    regenerate(_image_doc(str(src)), cfg, str(out))
    pdf = fitz.open(str(out))
    # image-backed (not a blank flow page): the source image is embedded
    assert len(pdf[0].get_images()) >= 1
    assert "halo dunia" in pdf[0].get_text()


def test_image_overlay_raster_output_keeps_format_and_size(tmp_path):
    src = tmp_path / "photo.png"
    _make_png(str(src), w=400, h=120)
    out = tmp_path / "photo.id.png"
    render_image_overlay(_image_doc(str(src)), Config(target_lang="id"), str(out))
    im = Image.open(str(out))
    assert im.format == "PNG"
    assert im.size == (400, 120)  # original pixel dimensions preserved


def test_image_same_as_source_outputs_translated_image(tmp_path):
    # same-as-source on an image -> a translated image (not a PDF), source ext kept
    src = tmp_path / "photo.png"
    _make_png(str(src))
    out = tmp_path / "photo.id.png"
    cfg = Config(target_lang="id", engine=Engine.ECHO, output_format=OutputFormat.SAME,
                 fidelity=Fidelity.LAYOUT)
    regenerate(_image_doc(str(src)), cfg, str(out))
    assert Image.open(str(out)).format == "PNG"


def test_overlay_uses_deskewed_render_path(tmp_path):
    # when a deskewed copy is provided, the overlay backgrounds on it (geometry matches the
    # OCR bboxes), not the original — verified via its distinct dimensions.
    src = tmp_path / "photo.png"
    _make_png(str(src), w=400, h=120)
    deskewed = tmp_path / "deskewed.png"
    _make_png(str(deskewed), w=420, h=140)  # different size -> proves which one was used
    out = tmp_path / "out.png"
    doc = _image_doc(str(src))
    doc.render_path = str(deskewed)
    render_image_overlay(doc, Config(target_lang="id"), str(out))
    assert Image.open(str(out)).size == (420, 140)


def test_no_text_returns_image_untouched(tmp_path):
    # OCR found nothing translatable -> the source image must come back byte-identical
    # (no re-encode, no deskew), not a re-rendered copy.
    import filecmp
    src = tmp_path / "photo.png"
    _make_png(str(src), w=300, h=100)
    out = tmp_path / "photo.id.png"
    doc = Document(source_path=str(src), mime="image", page_count=1)
    doc.blocks = []  # nothing to overlay
    render_image_overlay(doc, Config(target_lang="id"), str(out))
    assert filecmp.cmp(str(src), str(out), shallow=False)


def test_low_confidence_ocr_not_overlaid(tmp_path):
    # garbage OCR (low confidence) must not be painted over the original
    import filecmp
    src = tmp_path / "photo.png"
    _make_png(str(src), w=300, h=100)
    out = tmp_path / "photo.id.png"
    doc = Document(source_path=str(src), mime="image", page_count=1)
    doc.blocks = [Block(id="g", type=BlockType.PARAGRAPH, page=0, text="garble",
                        translated="halo", bbox=BBox(x0=10, y0=10, x1=200, y1=40),
                        confidence=Confidence(source="ocr", ocr=0.2))]
    render_image_overlay(doc, Config(target_lang="id"), str(out))
    assert filecmp.cmp(str(src), str(out), shallow=False)   # left untouched


def test_image_explicit_pdf_stays_pdf(tmp_path):
    src = tmp_path / "photo.png"
    _make_png(str(src))
    out = tmp_path / "out.pdf"
    cfg = Config(target_lang="id", engine=Engine.ECHO, output_format=OutputFormat.PDF,
                 fidelity=Fidelity.LAYOUT)
    regenerate(_image_doc(str(src)), cfg, str(out))
    assert len(fitz.open(str(out))[0].get_images()) >= 1
