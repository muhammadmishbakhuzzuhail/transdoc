# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Document layout analysis — detect a page's regions (text / title / figure / table /
formula / chart …) so non-text regions can be cropped verbatim (pixel-perfect math, diagrams,
charts) and only the text regions are translated and reflowed. This is the BabelDOC/DeepL
approach; without it we fall back to per-block heuristics (find_tables, _looks_formula).

Opt-in: needs the ``[paddleocr]`` extra (PaddleOCR PP-DocLayout, Apache-2.0). GPU is used when
available (the CPU oneDNN path is broken in paddlepaddle 3.3); see paddle_layout.py.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

# Labels PP-DocLayout emits that are NON-TEXT regions we crop from the source verbatim
# instead of re-typesetting (their internal layout — fractions, glyphs, vectors — can't be
# rebuilt from flattened text).
NON_TEXT_LABELS = frozenset({
    "image", "figure", "chart", "formula", "formula_number", "seal", "header_image",
    "table",  # a table is cropped verbatim too (cell reflow loses the grid for complex tables)
})


def _layout_python() -> str | None:
    """The interpreter to run PP-DocLayout in when paddle is not importable in-process.
    ``TRANSDOC_LAYOUT_PYTHON`` overrides; otherwise look for an isolated ``layout_venv``."""
    env = os.environ.get("TRANSDOC_LAYOUT_PYTHON")
    if env and Path(env).exists():
        return env
    for base in (Path.cwd(), Path(__file__).resolve().parents[3]):
        cand = base / "layout_venv" / "bin" / "python"
        if cand.exists():
            return str(cand)
    return None


def get_detector(name: str = "paddle"):
    """Return a layout detector. Prefers in-process paddle; if paddle is not installed here
    (the main env keeps torch, which collides with paddle's nccl), delegates to an isolated
    paddle interpreter via subprocess. Raises a clear error if neither is available.

    ``"auto"`` behaves like ``"paddle"`` — the caller (extract) wraps this in try/except so
    that when no paddle is reachable it silently degrades to the per-block heuristics."""
    if name not in ("paddle", "auto"):
        raise ValueError(f"unknown layout detector: {name}")
    if importlib.util.find_spec("paddle") is not None:
        from .paddle_layout import PaddleLayoutDetector
        return PaddleLayoutDetector()
    py = _layout_python()
    if py:
        from .paddle_layout import SubprocessLayoutDetector
        return SubprocessLayoutDetector(py)
    raise RuntimeError(
        "layout detection needs paddle: install the [paddleocr] extra in this env, or create "
        "an isolated paddle venv and point TRANSDOC_LAYOUT_PYTHON at its python "
        "(see the paddle-torch-venv-conflict note).")
