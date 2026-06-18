"""PP-StructureV3 structured extraction: regions with content (text / LaTeX / table HTML) and
reading order. Like the plain layout detector it runs in-process when paddle is importable,
else delegates to the isolated paddle interpreter via subprocess. See structure_detect.py and
ppstructurev3-region-router."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass

from . import _layout_python

_DPI = 150
_SCALE = 72.0 / _DPI
# Cap the longest rendered side so PP-StructureV3 fits in GPU memory. A full-res phone photo /
# large scan rendered at 150 DPI can exceed several thousand px and OOM a 6 GB GPU (audit: a
# newspaper JPG failed with CUDA OOM). Downscaling before inference keeps it on the GPU; region
# coords are scaled back to points via the per-page factor returned by render_page_array.
_MAX_PX = 2600


def render_page_array(page):
    """Render a PDF/image page to an RGB ndarray at _DPI, downscaled so its longest side is
    <= _MAX_PX (GPU memory cap). Returns (array, coord_scale) where region_pixels * coord_scale
    gives PDF points."""
    import io

    import numpy as np
    from PIL import Image

    pix = page.get_pixmap(dpi=_DPI)
    im = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    w, h = im.size
    longest = max(w, h)
    s = 1.0
    if longest > _MAX_PX:
        s = _MAX_PX / longest
        im = im.resize((max(1, round(w * s)), max(1, round(h * s))), Image.LANCZOS)
    return np.array(im), (_SCALE / s)


@dataclass
class StructRegion:
    label: str
    x0: float
    y0: float
    x1: float
    y1: float
    content: str
    order: int


_FIG = {"image", "figure", "chart", "seal", "stamp"}


def _iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    if inter <= 0:
        return 0.0
    area_a = max((a[2] - a[0]) * (a[3] - a[1]), 1e-6)
    area_b = max((b[2] - b[0]) * (b[3] - b[1]), 1e-6)
    return inter / (area_a + area_b - inter)


def parse_regions(root: dict, scale: float = _SCALE) -> list[dict]:
    """Normalize a PP-StructureV3 result dict into region dicts (bbox in points). Merges in
    figure/image boxes from layout_det_res, which parsing_res_list omits (they carry no text).
    ``scale`` converts render pixels to points (per-page when the render was downscaled)."""
    root = root.get("res", root)
    out = []
    for b in root.get("parsing_res_list", []):
        bb = b.get("block_bbox") or [0, 0, 0, 0]
        out.append({"label": b.get("block_label"), "bbox": [c * scale for c in bb],
                    "content": b.get("block_content", ""), "order": b.get("block_order") or 0})
    for box in root.get("layout_det_res", {}).get("boxes", []):
        if box.get("label") not in _FIG:
            continue
        bb = [c * scale for c in (box.get("coordinate") or [0, 0, 0, 0])]
        if any(_iou(bb, o["bbox"]) > 0.5 for o in out):
            continue
        above = [o["order"] for o in out if o["bbox"][1] < bb[1]]
        out.append({"label": box["label"], "bbox": bb, "content": "",
                    "order": (max(above) + 0.5) if above else -0.5})
    return out


def paddle_lang(source_lang: str | None) -> str:
    """Map a transdoc source language to the PaddleOCR language model code PP-StructureV3 should
    OCR with. PP-StructureV3 defaults to the Chinese model, which turns any non-Chinese scan to
    garbage (e.g. Devanagari -> stray CJK), so we always pass an explicit code: the mapped source
    language when known, else 'en' (Latin is the common case — a saner default than Chinese)."""
    src = (source_lang or "auto").lower()
    if src == "auto":
        return "en"
    from ..ocr.paddle import PADDLE_LANG
    return PADDLE_LANG.get(src, src)


class _InProcess:
    def __init__(self, lang: str | None = None):
        self._pipe = None
        self._lang = lang

    def _get(self):
        if self._pipe is None:
            from paddleocr import PPStructureV3
            self._pipe = PPStructureV3(lang=self._lang) if self._lang else PPStructureV3()
        return self._pipe

    def extract_pages(self, fdoc, pnos) -> dict[int, list[StructRegion]]:
        pipe = self._get()
        out: dict[int, list[StructRegion]] = {}
        for pno in pnos:
            arr, scale = render_page_array(fdoc[pno])
            res = list(pipe.predict(arr))
            regs: list[StructRegion] = []
            if res:
                for d in parse_regions(res[0].json, scale):
                    regs.append(StructRegion(d["label"], *d["bbox"], d["content"], d["order"]))
            out[pno] = regs
        return out


class _Subprocess:
    def __init__(self, python_exe: str, lang: str | None = None):
        self.python_exe = python_exe
        self._lang = lang

    def extract_pages(self, fdoc, pnos) -> dict[int, list[StructRegion]]:
        import json
        import os
        import subprocess
        import tempfile

        pnos = list(pnos)
        if not pnos:
            return {}
        pdf_path = fdoc.name
        if not pdf_path:
            raise RuntimeError("structured extraction needs a file-backed PDF")
        fd, out_path = tempfile.mkstemp(suffix=".json", prefix="transdoc-struct-")
        os.close(fd)
        try:
            cmd = [self.python_exe, "-m", "transdoc.layout.structure_detect",
                   pdf_path, out_path, *[str(p) for p in pnos]]
            if self._lang:
                cmd.append(f"--lang={self._lang}")
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                raise RuntimeError(
                    f"structure subprocess failed (exit {proc.returncode}): {proc.stderr[-500:]}")
            with open(out_path) as fh:
                raw = json.load(fh)
        finally:
            try:
                os.unlink(out_path)
            except OSError:
                pass
        return {int(p): [StructRegion(r["label"], *r["bbox"], r["content"], r["order"])
                         for r in regs]
                for p, regs in raw.items()}


def get_structure_extractor(lang: str | None = None):
    """In-process PP-StructureV3 if paddle is importable here, else the isolated subprocess.
    `lang` is the PaddleOCR language code to OCR with (see paddle_lang); None keeps PP-StructureV3's
    default. Raises if neither is available (caller decides whether to fall back)."""
    if importlib.util.find_spec("paddle") is not None:
        return _InProcess(lang)
    py = _layout_python()
    if py:
        return _Subprocess(py, lang)
    raise RuntimeError(
        "structured extraction needs paddle (PP-StructureV3): install the [paddleocr] extra or "
        "set TRANSDOC_LAYOUT_PYTHON to an isolated paddle venv.")
