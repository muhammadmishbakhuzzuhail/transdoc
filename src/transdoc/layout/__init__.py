"""Document layout analysis — detect a page's regions (text / title / figure / table /
formula / chart …) so non-text regions can be cropped verbatim (pixel-perfect math, diagrams,
charts) and only the text regions are translated and reflowed. This is the BabelDOC/DeepL
approach; without it we fall back to per-block heuristics (find_tables, _looks_formula).

Opt-in: needs the ``[paddleocr]`` extra (PaddleOCR PP-DocLayout, Apache-2.0). GPU is used when
available (the CPU oneDNN path is broken in paddlepaddle 3.3); see paddle_layout.py.
"""

from __future__ import annotations

# Labels PP-DocLayout emits that are NON-TEXT regions we crop from the source verbatim
# instead of re-typesetting (their internal layout — fractions, glyphs, vectors — can't be
# rebuilt from flattened text).
NON_TEXT_LABELS = frozenset({
    "image", "figure", "chart", "formula", "formula_number", "seal", "header_image",
    "table",  # a table is cropped verbatim too (cell reflow loses the grid for complex tables)
})


def get_detector(name: str = "paddle"):
    if name == "paddle":
        from .paddle_layout import PaddleLayoutDetector
        return PaddleLayoutDetector()
    raise ValueError(f"unknown layout detector: {name}")
