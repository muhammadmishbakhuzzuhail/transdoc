# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Word-alignment style transfer (PR-2): keep inline run styling aligned with the right words.

A mixed-style paragraph arrives as runs ("the ", **"red"**, " car"). Translating each run in
isolation (the previous strategy) keeps the styling but breaks word order and context: "the red
car" -> id "mobil merah itu" reorders, so a per-run translation lands the bold on the wrong word
(or mistranslates the fragment). Instead we translate the WHOLE block (good context + correct
order) and then push each source run's style onto the target words it aligns to.

The aligner is the awesome-align algorithm implemented directly on multilingual BERT: take the
layer-8 sub-word embeddings of the source and target separately, build the similarity matrix, and
keep the alignments that survive a softmax in BOTH directions (the intersection). This needs only
`transformers` + a non-gated mBERT checkpoint (~700MB, CPU-OK) — the upstream `awesome-align`
package is not cleanly pip-installable.

Lazy + optional: the model loads only when cfg.align_styles is on, and any failure (missing
package, model, or a too-sparse alignment) falls back to the existing per-run translation so output
is never worse than before.
"""

from __future__ import annotations

import os
import re

from ..ir import Block, Run, Style

_ALIGN_LAYER = 8        # awesome-align's recommended hidden layer for alignment embeddings
_THRESHOLD = 1e-3       # softmax mass below which an alignment is dropped
_MIN_COVERAGE = 0.3     # if fewer than this fraction of target words align, fall back


class WordAligner:
    _model = None
    _tok = None
    _ok = True

    @classmethod
    def release(cls) -> None:
        """Drop the mBERT aligner and free its memory after the align stage, so the next heavy
        stage (COMET QE) doesn't coexist with it. On a small box (~11 GB RAM) stacking paddle +
        mBERT + COMET overflows; each model runs in its OWN stage, so unloading between them keeps
        peak memory at one model, not the sum. Re-loads lazily if align runs again."""
        cls._model = None
        cls._tok = None
        cls._ok = True
        try:
            import gc
            gc.collect()
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def _load(self):
        if WordAligner._model is None and WordAligner._ok:
            try:
                from transformers import AutoModel, AutoTokenizer

                name = os.environ.get("ALIGN_MODEL", "bert-base-multilingual-cased")
                WordAligner._tok = AutoTokenizer.from_pretrained(name)
                WordAligner._model = AutoModel.from_pretrained(name)
                WordAligner._model.eval()
            except Exception:
                WordAligner._ok = False     # missing transformers / model / no network
        return WordAligner._model

    def align(self, src_words: list[str], tgt_words: list[str]) -> set[tuple[int, int]]:
        """Return {(src_word_idx, tgt_word_idx)} alignments (awesome-align argmax-intersection).
        Empty set when the model is unavailable or either side is empty."""
        model = self._load()
        if model is None or not src_words or not tgt_words:
            return set()
        try:
            import torch

            tok = WordAligner._tok
            ids_src, b2w_src = self._encode(src_words, tok)
            ids_tgt, b2w_tgt = self._encode(tgt_words, tok)
            if not b2w_src or not b2w_tgt:
                return set()
            with torch.no_grad():
                out_src = model(torch.tensor([ids_src]), output_hidden_states=True)
                out_tgt = model(torch.tensor([ids_tgt]), output_hidden_states=True)
            # drop [CLS] (first) and [SEP] (last); keep only the real sub-word rows
            es = out_src.hidden_states[_ALIGN_LAYER][0, 1:-1]
            et = out_tgt.hidden_states[_ALIGN_LAYER][0, 1:-1]
            dot = es @ et.transpose(-1, -2)
            srctgt = torch.softmax(dot, dim=-1)
            tgtsrc = torch.softmax(dot, dim=-2)
            inter = (srctgt > _THRESHOLD) * (tgtsrc > _THRESHOLD)
            align: set[tuple[int, int]] = set()
            for i, j in torch.nonzero(inter, as_tuple=False).tolist():
                align.add((b2w_src[i], b2w_tgt[j]))
            return align
        except Exception:
            return set()

    @staticmethod
    def _encode(words: list[str], tok):
        """Tokenize each word to sub-words and return (input_ids incl CLS/SEP, sub2word map).
        sub2word[k] = index of the word that sub-word k (after dropping CLS/SEP) belongs to."""
        ids: list[int] = [tok.cls_token_id]
        sub2word: list[int] = []
        for wi, w in enumerate(words):
            pieces = tok.encode(w, add_special_tokens=False)
            if not pieces:
                continue
            ids.extend(pieces)
            sub2word.extend([wi] * len(pieces))
        ids.append(tok.sep_token_id)
        return ids, sub2word


# --- word/style plumbing ---------------------------------------------------------------------

_WS = re.compile(r"\S+|\s+")


def _source_words(runs: list[Run]) -> tuple[list[str], list[Style]]:
    """Flatten runs to a list of words, each tagged with the style of its run."""
    words: list[str] = []
    styles: list[Style] = []
    for r in runs:
        for w in r.text.split():
            words.append(w)
            styles.append(r.style)
    return words, styles


def _restyle_block(b: Block, aligner: WordAligner) -> list[Run] | None:
    """Rebuild b.runs so each TARGET word carries the style of the source word it aligns to.
    Returns the new runs, or None to keep the existing per-run translation (sparse/failed align)."""
    src_words, src_styles = _source_words(b.runs)
    if not src_words or not (b.translated or "").strip():
        return None
    tgt_tokens = _WS.findall(b.translated)                 # words + whitespace, lossless
    tgt_word_idx = [k for k, t in enumerate(tgt_tokens) if not t.isspace()]
    tgt_words = [tgt_tokens[k] for k in tgt_word_idx]
    if not tgt_words:
        return None

    align = aligner.align(src_words, tgt_words)
    if not align:
        return None
    # how many target words got an alignment? bail out (fall back) if too sparse to be trustworthy
    aligned_tgt = {j for _, j in align}
    if len(aligned_tgt) < _MIN_COVERAGE * len(tgt_words):
        return None

    # per target word -> resolved style: majority of aligned source words (tie -> first source run)
    by_tgt: dict[int, list[int]] = {}
    for i, j in align:
        by_tgt.setdefault(j, []).append(i)
    word_style: list[Style | None] = []
    for j in range(len(tgt_words)):
        srcs = by_tgt.get(j)
        if not srcs:
            word_style.append(None)                        # unaligned -> inherit later
            continue
        # majority vote over the aligned source words' styles
        best = max(srcs, key=lambda i: sum(1 for k in srcs if src_styles[k] == src_styles[i]))
        word_style.append(src_styles[best])
    # carry the previous style forward across unaligned gaps (keeps runs contiguous)
    fallback = next((s for s in word_style if s is not None), b.style)
    last = fallback
    for k in range(len(word_style)):
        if word_style[k] is None:
            word_style[k] = last
        else:
            last = word_style[k]

    # walk all tokens in order, attach each to the current style, merge consecutive same-style runs
    runs: list[Run] = []
    wi = 0
    cur_style: Style | None = None
    cur_text = ""
    for tok in tgt_tokens:
        style = word_style[wi] if not tok.isspace() else cur_style
        if not tok.isspace():
            wi += 1
        if style is None:
            style = fallback
        if cur_style is None:
            cur_style, cur_text = style, tok
        elif style == cur_style:
            cur_text += tok
        else:
            runs.append(Run(text="", translated=cur_text, style=cur_style))
            cur_style, cur_text = style, tok
    if cur_text:
        runs.append(Run(text="", translated=cur_text, style=cur_style or fallback))
    return runs or None


def restyle_runs(doc, cfg) -> int:
    """Redistribute inline run styles onto the whole-block translation via word alignment.
    Only mixed-style blocks (>1 run) with a block-level translation are touched; uniform paragraphs
    and single-run blocks are left alone. Returns the count of blocks restyled."""
    if not getattr(cfg, "align_styles", False):
        return 0
    targets = [b for b in doc.blocks if len(b.runs) > 1 and (b.translated or "").strip()]
    if not targets:
        return 0
    aligner = WordAligner()
    n = 0
    for b in targets:
        new_runs = _restyle_block(b, aligner)
        if new_runs is not None:
            b.runs = new_runs
            n += 1
    return n
