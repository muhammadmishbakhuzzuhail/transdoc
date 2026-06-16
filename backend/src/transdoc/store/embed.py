"""Optional sentence-embedding backend for fuzzy TM reranking (PR-4).

Fuzzy TM match is source→source and monolingual (find a past source segment similar to the current
one), so a multilingual sentence encoder that scores semantic similarity is enough — no cross-lingual
alignment needed. The default model is ``paraphrase-multilingual-MiniLM-L12-v2`` (~470MB, 50+ langs,
CPU-friendly, 384-dim).

The dependency is OPTIONAL: ``sentence-transformers`` is not a core requirement. If it (or the model)
is unavailable, :meth:`Embedder.get` returns None and the caller falls back to a lexical similarity
score — fuzzy TM still works, just without semantic reranking (graceful degradation, per the spec).
"""

from __future__ import annotations


class Embedder:
    """Lazy, process-wide sentence encoder. Construction is attempted once per model name; on any
    failure (package missing, model download/load error) the name is cached as unavailable so we
    never retry per-segment."""

    _instances: dict[str, "Embedder | None"] = {}

    def __init__(self, model):
        self._model = model

    @classmethod
    def get(cls, model_name: str | None) -> "Embedder | None":
        """Return an encoder for ``model_name``, or None if disabled/unavailable (→ lexical fallback)."""
        if not model_name:
            return None
        if model_name not in cls._instances:
            cls._instances[model_name] = cls._load(model_name)
        return cls._instances[model_name]

    @staticmethod
    def _load(model_name: str) -> "Embedder | None":
        try:
            from sentence_transformers import SentenceTransformer
        except Exception:
            return None                             # optional dep absent -> lexical scoring only
        try:
            return Embedder(SentenceTransformer(model_name))
        except Exception:
            return None                             # model download/load failed -> degrade

    def similarity(self, query: str, candidates: list[str]) -> list[float]:
        """Cosine similarity (0..1) of ``query`` against each candidate. Embeddings are L2-normalized
        so the dot product is the cosine; returned clamped to [0, 1]."""
        if not candidates:
            return []
        vecs = self._model.encode([query, *candidates], normalize_embeddings=True)
        q = vecs[0]
        out = []
        for v in vecs[1:]:
            dot = float(sum(a * b for a, b in zip(q, v)))
            out.append(max(0.0, min(1.0, dot)))
        return out
