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


@dataclass
class StructRegion:
    label: str
    x0: float
    y0: float
    x1: float
    y1: float
    content: str
    order: int


class _InProcess:
    def __init__(self):
        self._pipe = None

    def _get(self):
        if self._pipe is None:
            from paddleocr import PPStructureV3
            self._pipe = PPStructureV3()
        return self._pipe

    def extract_pages(self, fdoc, pnos) -> dict[int, list[StructRegion]]:
        import io

        import numpy as np
        from PIL import Image

        pipe = self._get()
        out: dict[int, list[StructRegion]] = {}
        for pno in pnos:
            pix = fdoc[pno].get_pixmap(dpi=_DPI)
            arr = np.array(Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB"))
            res = list(pipe.predict(arr))
            regs: list[StructRegion] = []
            if res:
                root = res[0].json
                root = root.get("res", root)
                for b in root.get("parsing_res_list", []):
                    bb = b.get("block_bbox") or [0, 0, 0, 0]
                    regs.append(StructRegion(
                        b.get("block_label"), *[c * _SCALE for c in bb],
                        b.get("block_content", ""), b.get("block_order") or 0))
            out[pno] = regs
        return out


class _Subprocess:
    def __init__(self, python_exe: str):
        self.python_exe = python_exe

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


def get_structure_extractor():
    """In-process PP-StructureV3 if paddle is importable here, else the isolated subprocess.
    Raises if neither is available (caller decides whether to fall back)."""
    if importlib.util.find_spec("paddle") is not None:
        return _InProcess()
    py = _layout_python()
    if py:
        return _Subprocess(py)
    raise RuntimeError(
        "structured extraction needs paddle (PP-StructureV3): install the [paddleocr] extra or "
        "set TRANSDOC_LAYOUT_PYTHON to an isolated paddle venv.")
