# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""PP-DocLayout (PaddleOCR) region detector — Apache-2.0, GPU ~80 ms/page.

Detects a page's regions and returns them in PDF points so the extractor can decide which
blocks are inside a non-text region (crop verbatim) vs a text region (translate + reflow).

NOTE: the CPU oneDNN backend of paddlepaddle 3.3 raises on this model, so we run on GPU when
``paddle.is_compiled_with_cuda()`` (the layout net is tiny — it fits a 6 GB card, unlike the
0.9B VL). Falls back to CPU only if no CUDA build is present.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

# Rasterisation DPI for layout detection; bboxes are scaled back to points by 72/DPI.
_DPI = 150


@dataclass
class Region:
    label: str
    x0: float
    y0: float
    x1: float
    y1: float


class PaddleLayoutDetector:
    name = "paddle"

    def __init__(self, model_name: str = "PP-DocLayout-L"):
        self._model = None
        self._model_name = model_name

    def _get(self):
        if self._model is None:
            import paddle
            from paddlex import create_model
            device = "gpu:0" if paddle.is_compiled_with_cuda() else "cpu"
            self._model = create_model(model_name=self._model_name, device=device)
        return self._model

    def detect(self, page) -> list[Region]:
        """Detect regions on a PyMuPDF page; returns boxes in PDF points."""
        import numpy as np
        from PIL import Image

        pix = page.get_pixmap(dpi=_DPI)
        arr = np.array(Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB"))
        result = list(self._get().predict(arr, batch_size=1))
        if not result:
            return []
        scale = 72.0 / _DPI
        regions: list[Region] = []
        for b in result[0]["boxes"]:
            x0, y0, x1, y1 = (c * scale for c in b["coordinate"])
            regions.append(Region(b["label"], x0, y0, x1, y1))
        return regions

    def detect_pages(self, fdoc, pnos) -> dict[int, list[Region]]:
        return {pno: self.detect(fdoc[pno]) for pno in pnos}


class SubprocessLayoutDetector:
    """Run PP-DocLayout in an isolated paddle interpreter (keeps paddle out of the torch venv).

    All requested pages are detected in ONE subprocess call so paddle is imported once.
    """

    name = "paddle"

    def __init__(self, python_exe: str):
        self.python_exe = python_exe

    def detect(self, page) -> list[Region]:
        return self.detect_pages(page.parent, [page.number]).get(page.number, [])

    def detect_pages(self, fdoc, pnos) -> dict[int, list[Region]]:
        import json
        import os
        import subprocess
        import tempfile

        pnos = list(pnos)
        if not pnos:
            return {}
        pdf_path = fdoc.name
        if not pdf_path:
            raise RuntimeError("subprocess layout needs a file-backed PDF (fdoc.name is empty)")
        fd, out_path = tempfile.mkstemp(suffix=".json", prefix="transdoc-layout-")
        os.close(fd)
        try:
            cmd = [self.python_exe, "-m", "transdoc.layout.subprocess_detect",
                   pdf_path, out_path, *[str(p) for p in pnos]]
            # Bound the subprocess so a wedged paddle can't block the worker (and thus the
            # serialised job queue) indefinitely.
            timeout = float(os.environ.get("TRANSDOC_LAYOUT_TIMEOUT", "0")) or max(300.0, 120.0 * len(pnos))
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            except subprocess.TimeoutExpired as e:
                raise RuntimeError(f"layout subprocess timed out after {timeout:.0f}s") from e
            if proc.returncode != 0:
                raise RuntimeError(
                    f"layout subprocess failed (exit {proc.returncode}): {proc.stderr[-500:]}")
            with open(out_path) as fh:
                raw = json.load(fh)
        finally:
            try:
                os.unlink(out_path)
            except OSError:
                pass
        return {int(p): [Region(*r) for r in regs] for p, regs in raw.items()}
