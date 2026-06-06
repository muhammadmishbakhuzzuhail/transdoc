"""Reference-free translation quality estimation (QE).

Scores each (source, translation) pair without needing a human reference, so we can flag
weak segments for human review and (optionally) retranslate them. Default model is
COMET-Kiwi (Unbabel/wmt22-cometkiwi-da) — the standard reference-free QE model.

Lazy + optional: importing pulls the comet package + a ~2GB model, so QE only runs when
cfg.quality_check is on. Gracefully no-ops if the package/model is unavailable.
"""

from __future__ import annotations

import os


class QualityEstimator:
    _model = None
    _ok = True

    def _load(self):
        if QualityEstimator._model is None and QualityEstimator._ok:
            try:
                from comet import download_model, load_from_checkpoint

                name = os.environ.get("QE_MODEL", "Unbabel/wmt22-cometkiwi-da")
                path = download_model(name)
                QualityEstimator._model = load_from_checkpoint(path)
            except Exception:
                QualityEstimator._ok = False  # missing package / gated model / no token
        return QualityEstimator._model

    def score(self, pairs: list[tuple[str, str]]) -> list[float | None]:
        """pairs = [(source, translation), ...] -> [0..1 score or None if unavailable]."""
        model = self._load()
        if model is None:
            return [None] * len(pairs)
        data = [{"src": s, "mt": t} for s, t in pairs]
        try:
            out = model.predict(data, batch_size=8, gpus=1 if _has_cuda() else 0)
            return [float(x) for x in out["scores"]]
        except Exception:
            return [None] * len(pairs)


def _has_cuda() -> bool:
    try:
        import torch

        return torch.cuda.is_available()
    except Exception:
        return False


def annotate_quality(doc, cfg) -> None:
    """Score every translated block; write the score into confidence and flag the weak ones."""
    if not getattr(cfg, "quality_check", False):
        return
    blocks = [b for b in doc.blocks if b.translated and b.text.strip()]
    if not blocks:
        return
    qe = QualityEstimator()
    scores = qe.score([(b.text, b.translated) for b in blocks])
    for b, s in zip(blocks, scores):
        if s is None:
            continue
        b.confidence.translation = round(s, 3)
        if s < cfg.flag_threshold:
            b.flags["low_translation_quality"] = f"QE {s:.0%}"
