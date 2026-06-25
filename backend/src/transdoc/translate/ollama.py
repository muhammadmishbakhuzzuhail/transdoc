# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
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

    def _few_shot(self, cfg: Config, src: str | None,
                  texts: list[str]) -> list[tuple[str, str]]:
        """Feedback flywheel: the user's most similar CONFIRMED corrections, to show the model how
        this user wants things translated. Per-chunk, dedup, capped at cfg.few_shot_k. Best-effort —
        returns [] if persistence/TM is off or nothing relevant."""
        if not getattr(cfg, "few_shot", False) or cfg.few_shot_k <= 0:
            return []
        from ..store.tm import TMStore
        tm = TMStore.get()
        if tm is None or not hasattr(tm, "fuzzy_search"):
            return []
        embedder = None
        if cfg.embed_model:
            try:
                from ..store.embed import Embedder
                embedder = Embedder.get(cfg.embed_model)
            except Exception:
                embedder = None
        seen: dict[str, tuple[str, str, float]] = {}
        for text in texts:
            try:
                hits = tm.fuzzy_search(text, cfg.target_lang, src_lang=src or "",
                                       domain=cfg.domain, embedder=embedder, limit=cfg.few_shot_k,
                                       min_score=0.6, confirmed_only=True)
            except Exception:
                continue
            for s, t, sc in hits:
                if s not in seen or sc > seen[s][2]:
                    seen[s] = (s, t, sc)
        ranked = sorted(seen.values(), key=lambda r: r[2], reverse=True)[:cfg.few_shot_k]
        return [(s, t) for s, t, _ in ranked]

    def _system(self, cfg: Config, src: str | None,
                examples: list[tuple[str, str]] | None = None) -> str:
        gl = ""
        if cfg.glossary:
            pairs = "; ".join(f"{k} -> {v}" for k, v in cfg.glossary.items())
            gl = f" Enforce this glossary exactly (source -> target): {pairs}."
        fs = ""
        if examples:
            ex = "; ".join(f'"{s}" -> "{t}"' for s, t in examples)
            fs = (" Here is how THIS user has corrected similar translations before — match their "
                  f"wording, terminology and register: {ex}.")
        return (
            "You are a professional document translator. Translate from "
            f"{src or 'the detected language'} to {cfg.target_lang}. "
            f"Domain: {cfg.domain}. Register: {cfg.register.value}. "
            "The items are consecutive text from one document; use the surrounding context only to "
            "stay coherent and consistent — do NOT translate the context, only the items. "
            "Translate meaning idiomatically. Preserve numbers, dates, IDs, codes, URLs and proper "
            "nouns exactly. Keep any [PH<n>] placeholders verbatim and in place. Do not add, remove, "
            "merge or reorder items." + gl + fs +
            ' Return ONLY a JSON object: {"translations": {"<id>": "<translated text>", ...}} '
            "with exactly one entry per item id given."
        )

    def _call(self, cfg: Config, system: str, user: str, temperature: float = 0.0,
              fmt: str | None = "json") -> str:
        payload = {
            "model": cfg.ollama_model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "stream": False,
            "options": {"temperature": temperature, "num_ctx": cfg.ollama_num_ctx},
        }
        if fmt:                       # JSON-mode for the structured calls; plain text (fmt=None) for
            payload["format"] = fmt   # free-form output like OCR correction
        body = json.dumps(payload).encode("utf-8")
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
            content = content.split("```")[1].removeprefix("json").strip()
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
        examples = self._few_shot(cfg, src, [s for _, s in chunk])
        user = json.dumps({
            "context_before": [{"source": s, "translation": t} for s, t in prev_pairs],
            "items": [{"id": i, "text": s} for i, s in chunk],
            "context_after": following,
        }, ensure_ascii=False)
        content = self._call(cfg, self._system(cfg, src, examples), user)
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

    def translate_one(self, text: str, cfg: Config, src: str | None = None,
                      prev_pairs: list[tuple[str, str]] | None = None,
                      following: list[str] | None = None) -> str:
        """Translate a SINGLE segment with explicit neighbour context (already-translated previous +
        source following). Used by the hybrid QE-gate to re-translate one weak segment in context,
        without re-translating its neighbours."""
        return self._translate_once(cfg, src, [("0", text)], prev_pairs or [], following or [])[0]

    def alternatives(self, text: str, cfg: Config, src: str | None = None, n: int = 3,
                     style: str | None = None) -> list[str]:
        """Generate up to ``n`` DISTINCT alternative translations of one segment (review aid). Higher
        temperature for variety; preserves numbers/placeholders. ``style`` (a mode preset) steers all
        alternatives toward one register instead of varying it. Raises OllamaError if unavailable."""
        n = max(1, min(5, n))
        from .suggest import STYLE_DIRECTIVES
        if style and style in STYLE_DIRECTIVES:
            steer = (f"Write every alternative in a {STYLE_DIRECTIVES[style]} style; vary only the "
                     "phrasing/word choice, not the register.")
        else:
            steer = "Vary the phrasing/word choice/register across alternatives."
        system = (
            "You are a professional translator. Produce alternative translations from "
            f"{src or 'the detected language'} to {cfg.target_lang} of the given text. {steer} All "
            "faithful to the meaning. "
            "Preserve numbers, dates, IDs, URLs, proper nouns and any [PH<n>] placeholders exactly. "
            f'Return ONLY a JSON object: {{"alternatives": ["...", "..."]}} with {n} distinct items.'
        )
        user = json.dumps({"text": text, "n": n}, ensure_ascii=False)
        content = self._call(cfg, system, user, temperature=0.8)
        if content.startswith("```"):
            content = content.split("```")[1].removeprefix("json").strip()
        obj = json.loads(content)
        alts = obj.get("alternatives", obj) if isinstance(obj, dict) else obj
        if not isinstance(alts, list):
            raise OllamaError("alternatives not a list")
        seen, out = set(), []
        for a in alts:
            s = str(a).strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
        return out[:n]

    def unload(self, cfg: Config) -> None:
        """Best-effort: evict the model from (V)RAM now instead of letting Ollama keep it resident
        (~5min by default). On a 6 GB GPU the ~5.5 GB the LLM squats causes 'device memory nearly
        full' OOM when the next GPU consumer (COMET QE / paddle OCR) also wants the card. Call after
        an LLM phase so only one big model is resident at a time."""
        body = json.dumps({"model": cfg.ollama_model, "keep_alive": 0}).encode("utf-8")
        try:
            req = urllib.request.Request(self._host(cfg) + "/api/generate", data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=cfg.ollama_timeout):
                pass
        except Exception:
            pass

    def correct_ocr(self, text: str, cfg: Config, src: str | None = None) -> str:
        """Conservatively fix OCR errors in `text` WITHOUT translating or paraphrasing — same
        language, same content, only obvious scanning mistakes (l/1, rn/m, merged/split words, stray
        punctuation). Returns the corrected text, or the original on any failure / declined edit."""
        lang = src or "the original"
        system = (
            "You are an OCR post-corrector. The text was extracted from a scanned document and may "
            "contain OCR errors: swapped/merged/split characters (l/1, rn/m), broken words, stray "
            f"punctuation. Fix ONLY obvious OCR mistakes and keep the original {lang} language. Do "
            "NOT translate, do NOT paraphrase, do NOT add, remove, or reorder content, do NOT "
            "explain. If the text already looks correct or you are unsure, return it unchanged. "
            "Output only the corrected text, nothing else."
        )
        try:
            out = self._call(cfg, system, text, fmt=None).strip()   # free-form, not JSON-mode
        except OllamaError:
            return text
        return out or text

    def translate_batch(self, texts: list[str], cfg: Config,
                        src: str | None = None) -> list[str]:
        """Segment-independent path (used for auto-glossary term renderings + as a generic API).
        No carried context; still id-aligned JSON, split-on-misalignment."""
        if not texts:
            return []
        results: list[str | None] = [None] * len(texts)
        self._translate_span(cfg, src, texts, results, 0, len(texts))
        return [r if r is not None else t for r, t in zip(results, texts)]
