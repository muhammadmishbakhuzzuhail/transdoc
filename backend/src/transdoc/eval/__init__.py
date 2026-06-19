# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Translation-quality evaluation harness.

Turns "the output looks good" into measurable, reproducible numbers: structure preservation
(formulas/tables/figures), rendering fidelity, OCR CER/WER and translation chrF against gold
sidecars. Run over a corpus to produce a scorecard, and diff against a saved baseline to gate
regressions in CI.

    python -m transdoc.eval.harness corpus/synthetic --baseline eval_baseline.json
"""

from .metrics import cer, chrf, edit_distance, pdf_fidelity, structure_metrics, wer

__all__ = ["cer", "chrf", "edit_distance", "pdf_fidelity", "structure_metrics", "wer"]
