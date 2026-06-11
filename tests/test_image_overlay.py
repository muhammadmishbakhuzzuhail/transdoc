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
    cfg = Config(target_lang="id", engine=Engine.ECHO,
                 output_format=OutputFormat.PDF, fidelity=Fidelity.AUTO)
    regenerate(_image_doc(str(src)), cfg, str(out))
    pdf = fitz.open(str(out))
    # image-backed (not a blank flow page): the source image is embedded
    assert len(pdf[0].get_images()) >= 1
    assert "halo dunia" in pdf[0].get_text()


def test_image_same_as_source_becomes_pdf_overlay(tmp_path):
    src = tmp_path / "photo.png"
    _make_png(str(src))
    out = tmp_path / "out.pdf"
    cfg = Config(target_lang="id", engine=Engine.ECHO, output_format=OutputFormat.SAME)
    regenerate(_image_doc(str(src)), cfg, str(out))
    assert len(fitz.open(str(out))[0].get_images()) >= 1
