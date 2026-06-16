"""Ollama local-LLM translator — document-level, context-aware (zero-cost, offline, private).

Unlike the segment-independent NMT engines, this carries a sliding window of neighbours so the
translation stays coherent and terminology stays consistent across a document (the quality gap
NMT can't close). See GLOSSARY-TM-FEEDBACK-SPEC.md, Area A.

Design (all settled with the maintainer):
- sliding window: N previous segments (already TRANSLATED, carried for consistency) + N following
  (source) shown read-only around each batch;
- numbered segments -> structured JSON {id: translation}; validated 1:1, mismatch -> retry -> fail;
- adaptive batching under the model's num_ctx;
- deterministic (temperature=0) so the context-hash TM cache (PR-A2) stays valid;
- retry 2x with backoff, then HARD-FAIL (explicit error; no silent NMT fallback);
- glossary passed as a prompt instruction; verbatim tokens stay protected as [PH] placeholders
  (handled by the caller) and the prompt is told to keep them untouched.

Talks to Ollama's /api/chat over stdlib urllib (no extra dependency). Model/host/timeout/num_ctx
come from Config (host also overridable via OLLAMA_HOST).
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from ..config import Config


class OllamaError(RuntimeError):
    """Ollama unreachable / timed out / returned unusable output after retries (hard-fail)."""


class OllamaTranslator:
    name = "ollama"
    doc_context = True          # base.translate_document routes the body through translate_segments
    cacheable = False           # PR-A1: no caching yet; context-hash TM cache lands in PR-A2

    _RETRIES = 2
    _BACKOFF = 1.5              # seconds, multiplied per attempt

    def _host(self, cfg: Config) -> str:
        # OLLAMA_HOST (Ollama's own convention) is often scheme-less "host:port"; urllib needs a
        # scheme, so default to http:// when none is given.
        h = (os.environ.get("OLLAMA_HOST") or cfg.ollama_host).rstrip("/")
        if not h.startswith(("http://", "https://")):
            h = "http://" + h
        return h

    def _system(self, cfg: Config, src: str | None) -> str:
        gl = ""
        if cfg.glossary:
            pairs = "; ".join(f"{k} -> {v}" for k, v in cfg.glossary.items())
            gl = f" Enforce this glossary exactly (source -> target): {pairs}."
        return (
            "You are a professional document translator. Translate from "
            f"{src or 'the detected language'} to {cfg.target_lang}. "
            f"Domain: {cfg.domain}. Register: {cfg.register.value}. "
            "The items are consecutive text from one document; use the surrounding context only to "
            "stay coherent and consistent — do NOT translate the context, only the items. "
            "Translate meaning idiomatically. Preserve numbers, dates, IDs, codes, URLs and proper "
            "nouns exactly. Keep any [PH<n>] placeholders verbatim and in place. Do not add, remove, "
            "merge or reorder items." + gl +
            ' Return ONLY a JSON object: {"translations": {"<id>": "<translated text>", ...}} '
            "with exactly one entry per item id given."
        )

    def _call(self, cfg: Config, system: str, user: str) -> str:
        body = json.dumps({
            "model": cfg.ollama_model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0, "num_ctx": cfg.ollama_num_ctx},
        }).encode("utf-8")
        url = self._host(cfg) + "/api/chat"
        last: Exception | None = None
        for attempt in range(self._RETRIES + 1):
            try:
                req = urllib.request.Request(url, data=body,
                                             headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=cfg.ollama_timeout) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                content = (payload.get("message") or {}).get("content", "")
                if content.strip():
                    return content
                last = OllamaError("empty response")
            except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as e:
                last = e
            if attempt < self._RETRIES:
                time.sleep(self._BACKOFF * (attempt + 1))
        raise OllamaError(f"Ollama call failed after {self._RETRIES + 1} attempts: {last}")

    @staticmethod
    def _parse(content: str, ids: list[str]) -> list[str]:
        """Parse {"translations": {id: text}} and return values in `ids` order. Raises on mismatch."""
        if content.startswith("```"):
            content = content.split("```")[1].lstrip("json").strip()
        obj = json.loads(content)
        table = obj.get("translations", obj) if isinstance(obj, dict) else {}
        if not isinstance(table, dict):
            raise OllamaError("translations not an object")
        out = []
        for i in ids:
            if i not in table:
                raise OllamaError(f"missing id {i}")
            out.append(str(table[i]))
        return out

    def _translate_once(self, cfg: Config, src: str | None, chunk: list[tuple[str, str]],
                        prev_pairs: list[tuple[str, str]], following: list[str]) -> list[str]:
        """One model call for a chunk. chunk: [(id, source)]; prev_pairs: [(source, translation)]
        carried context; following: next source segments (read-only). Returns translations in chunk
        order, or raises OllamaError if the response can't be aligned 1:1 to the requested ids."""
        user = json.dumps({
            "context_before": [{"source": s, "translation": t} for s, t in prev_pairs],
            "items": [{"id": i, "text": s} for i, s in chunk],
            "context_after": following,
        }, ensure_ascii=False)
        content = self._call(cfg, self._system(cfg, src), user)
        try:
            return self._parse(content, [i for i, _ in chunk])
        except (OllamaError, json.JSONDecodeError, ValueError) as e:
            raise OllamaError(str(e)) from e

    def _translate_span(self, cfg: Config, src: str | None, texts: list[str],
                        results: list[str | None], lo: int, hi: int) -> None:
        """Translate texts[lo:hi] in place into `results`, carrying translated neighbours as context.
        On an alignment failure the span is SPLIT and each half retried (retrying the same prompt at
        temperature 0 would just reproduce the failure); a single segment that still fails to align
        hard-fails (no silent fallback). This keeps one dropped id from sinking the whole document."""
        w = max(0, cfg.llm_context_window)
        chunk = [(str(i), texts[i]) for i in range(lo, hi)]
        prev_pairs = [(texts[j], results[j]) for j in range(max(0, lo - w), lo)
                      if results[j] is not None]
        following = texts[hi:hi + w]
        try:
            out = self._translate_once(cfg, src, chunk, prev_pairs, following)
            for i, t in zip(range(lo, hi), out):
                results[i] = t
        except OllamaError:
            if hi - lo <= 1:
                raise
            mid = (lo + hi) // 2
            self._translate_span(cfg, src, texts, results, lo, mid)
            self._translate_span(cfg, src, texts, results, mid, hi)

    def translate_segments(self, texts: list[str], cfg: Config,
                           src: str | None = None) -> list[str]:
        """Context-aware path: translate ORDERED document segments, carrying translated neighbours.
        Packs segments into token-budget chunks; a chunk that fails id-alignment is split + retried."""
        if not texts:
            return []
        char_budget = max(2000, cfg.ollama_num_ctx * 2)     # rough: ~2 chars/token of input room
        results: list[str | None] = [None] * len(texts)
        i = 0
        while i < len(texts):
            end = i + 1
            size = len(texts[i])
            while end < len(texts) and size + len(texts[end]) <= char_budget:
                size += len(texts[end])
                end += 1
            self._translate_span(cfg, src, texts, results, i, end)
            i = end
        return [r if r is not None else "" for r in results]

    def translate_batch(self, texts: list[str], cfg: Config,
                        src: str | None = None) -> list[str]:
        """Segment-independent path (used for auto-glossary term renderings + as a generic API).
        No carried context; still id-aligned JSON, split-on-misalignment."""
        if not texts:
            return []
        results: list[str | None] = [None] * len(texts)
        self._translate_span(cfg, src, texts, results, 0, len(texts))
        return [r if r is not None else t for r, t in zip(results, texts)]
