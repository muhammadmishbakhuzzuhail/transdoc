"""Objective quality metrics for the eval harness — pure, deterministic, dependency-light.

Three families:
  - translation:  chrF (character n-gram F-score, reference-based, no model download).
  - OCR / text:   CER / WER via a builtin Levenshtein (jiwer-equivalent, no heavy dep so it
                  runs in CI; jiwer is the validated reference implementation if you want it).
  - structure:    counts of formulas / tables / cells / figures + reading-order monotonicity
                  read straight off the IR — this is what catches a regression like the
                  reading_order bug that silently dropped the structured path to the heuristic
                  extractor (formula count would crater).
  - rendering:    pdf_fidelity — text-on-image overwrites, sub-6pt (illegible) and off-page
                  spans, by PyMuPDF geometry (no paddle/torch).

Everything here is reused by scripts/bench_quality.py and scripts/qa_fidelity.py so there is
one source of truth for each metric.
"""

from __future__ import annotations

from collections import Counter

# --------------------------------------------------------------------------- translation


def _char_ngrams(s: str, n: int) -> list[str]:
    s = s.lower()
    return [s[i:i + n] for i in range(len(s) - n + 1)] if len(s) >= n else []


def chrf(ref: str, hyp: str, max_n: int = 6, beta: float = 2.0) -> float:
    """chrF: average char n-gram (1..max_n) F-score, recall-weighted (beta=2). 0..100."""
    fs = []
    for n in range(1, max_n + 1):
        r, h = Counter(_char_ngrams(ref, n)), Counter(_char_ngrams(hyp, n))
        if not r or not h:
            continue
        match = sum((r & h).values())
        prec = match / sum(h.values())
        rec = match / sum(r.values())
        if prec + rec == 0:
            fs.append(0.0)
            continue
        fs.append((1 + beta ** 2) * prec * rec / (beta ** 2 * prec + rec))
    return 100 * sum(fs) / len(fs) if fs else 0.0


# --------------------------------------------------------------------------- OCR / text


def edit_distance(a: list, b: list) -> int:
    """Levenshtein distance over two sequences (chars for CER, words for WER)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cer(ref: str, hyp: str) -> float:
    """Character error rate: edits / reference length. 0 = perfect; can exceed 1."""
    ref = ref or ""
    if not ref:
        return 0.0 if not (hyp or "") else 1.0
    return edit_distance(list(ref), list(hyp or "")) / len(ref)


def wer(ref: str, hyp: str) -> float:
    """Word error rate: word edits / reference word count. 0 = perfect; can exceed 1."""
    rw, hw = (ref or "").split(), (hyp or "").split()
    if not rw:
        return 0.0 if not hw else 1.0
    return edit_distance(rw, hw) / len(rw)


# --------------------------------------------------------------------------- tables


def _ir_table_tokens(table) -> list[str]:
    """IR Table -> ordered structural tokens (row markers + per-cell span signature). Captures
    grid shape + merged-cell spans, ignores cell text (this is TEDS-Struct)."""
    toks: list[str] = []
    for row in table.rows:
        toks.append("<tr>")
        for c in row:
            toks.append(f"<c r{getattr(c, 'rowspan', 1)} c{getattr(c, 'colspan', 1)}>")
    return toks


def _html_table_tokens(html: str) -> list[str]:
    """Reference HTML table -> the same structural token sequence."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html or "", "html.parser")
    toks: list[str] = []
    for tr in soup.find_all("tr"):
        toks.append("<tr>")
        for cell in tr.find_all(["td", "th"]):
            r = int(cell.get("rowspan", 1) or 1)
            c = int(cell.get("colspan", 1) or 1)
            toks.append(f"<c r{r} c{c}>")
    return toks


def table_teds(ref_html: str, hyp_table) -> float:
    """Table-structure similarity (0..1, 1 = identical grid), a dependency-free TEDS-Struct
    approximation: sequence edit distance over the row/cell/span token streams of the reference
    HTML table and the extracted IR Table. Catches dropped/added cells & rows and wrong
    row/colspans — which cell-counts alone miss. (True TEDS uses tree-edit; for the mostly-ordered
    row/cell structure of tables this sequence-edit tracks the same errors without an APTED dep.)"""
    ref = _html_table_tokens(ref_html)
    hyp = _ir_table_tokens(hyp_table) if hyp_table is not None else []
    if not ref and not hyp:
        return 1.0
    return 1.0 - edit_distance(ref, hyp) / max(len(ref), len(hyp), 1)


# --------------------------------------------------------------------------- layout


def bbox_iou(a, b) -> float:
    """Intersection-over-union of two (x0,y0,x1,y1) boxes (0..1)."""
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    if inter <= 0:
        return 0.0
    aa = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    ab = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = aa + ab - inter
    return inter / union if union > 0 else 0.0


def layout_match(refs, hyps, iou_thresh: float = 0.5) -> dict:
    """Greedy-match extracted layout regions to reference regions by IoU and report detection
    quality: mean IoU of matched boxes, precision/recall/F1 at the IoU threshold, and the label
    accuracy of matched pairs. refs/hyps are lists of (label, (x0,y0,x1,y1)). This is the missing
    POSITIONAL metric — counts say "5 regions", this says whether they're in the right places with
    the right types (region drift/mis-typing that overlay-redaction & reconstruct depend on)."""
    pairs = sorted(((bbox_iou(rb, hb), i, j)
                    for i, (_, rb) in enumerate(refs)
                    for j, (_, hb) in enumerate(hyps)),
                   key=lambda t: t[0], reverse=True)
    used_r, used_h, matched = set(), set(), []
    for iou, i, j in pairs:
        if iou <= 0 or i in used_r or j in used_h:
            continue
        used_r.add(i)
        used_h.add(j)
        matched.append((iou, i, j))
    tp = sum(1 for iou, _, _ in matched if iou >= iou_thresh)
    prec = tp / len(hyps) if hyps else (1.0 if not refs else 0.0)
    rec = tp / len(refs) if refs else (1.0 if not hyps else 0.0)
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    mean_iou = (sum(iou for iou, _, _ in matched) / len(matched) if matched
                else (1.0 if not refs and not hyps else 0.0))
    label_acc = (sum(1 for iou, i, j in matched
                     if iou >= iou_thresh and refs[i][0] == hyps[j][0]) / tp if tp
                 else (1.0 if not refs else 0.0))
    return {"mean_iou": mean_iou, "precision": prec, "recall": rec, "f1": f1,
            "label_acc": label_acc, "matched": tp, "refs": len(refs), "hyps": len(hyps)}


# --------------------------------------------------------------------------- structure


def structure_metrics(doc) -> dict:
    """Counts read straight off the IR. The preservation signals (formulas/tables/figures)
    are what regress when the structured path breaks."""
    from ..ir import BlockType

    by_type: dict[str, int] = {}
    cells = 0
    for b in doc.blocks:
        by_type[b.type.value] = by_type.get(b.type.value, 0) + 1
        if b.type == BlockType.TABLE and b.table:
            cells += sum(len(r) for r in b.table.rows)
    # Read reading_order in the blocks' STORED order (not ordered_blocks(), which sorts by it
    # and would always look monotonic). A well-formed extractor appends in reading order, so a
    # non-monotonic sequence here means the order got corrupted (the class of bug that silently
    # dropped the structured path to the heuristic extractor).
    orders = [b.reading_order for b in doc.blocks]
    return {
        "blocks": len(doc.blocks),
        "by_type": by_type,
        "formulas": by_type.get("formula", 0),
        "tables": by_type.get("table", 0),
        "table_cells": cells,
        "figures": by_type.get("figure", 0),
        "translatable": len(doc.translatable_blocks()),
        "flagged": len(doc.flagged_blocks()),
        "pages": doc.page_count,
        "reading_order_monotonic": orders == sorted(orders),
    }


# --------------------------------------------------------------------------- rendering


def _overlap(a, b) -> float:
    inter = a & b
    if not inter or a.is_empty:
        return 0.0
    return abs(inter) / max(abs(a), 1e-6)


def pdf_fidelity(path: str) -> dict:
    """Per-page rendering defects in an output PDF, by geometry:
      - overwrite: a text span sitting on top of an embedded image (figure/table crop)
      - tiny:      a span rendered < 6 pt (illegible)
      - overflow:  a span leaving the page rect
    Pure PyMuPDF — no paddle/torch."""
    import fitz

    d = fitz.open(path)
    findings: dict = {"overwrite": [], "tiny": [], "overflow": [], "pages": []}
    try:
        for pno in range(d.page_count):
            page = d[pno]
            pr = page.rect
            imgs = [fitz.Rect(b["bbox"]) for b in page.get_image_info(xrefs=False)]
            sizes: list[float] = []
            nspans = 0
            for blk in page.get_text("dict")["blocks"]:
                for line in blk.get("lines", []):
                    for sp in line.get("spans", []):
                        txt = sp["text"].strip()
                        if not txt:
                            continue
                        nspans += 1
                        r = fitz.Rect(sp["bbox"])
                        sizes.append(sp["size"])
                        for ir in imgs:
                            if _overlap(r, ir) > 0.35:
                                findings["overwrite"].append(
                                    (pno + 1, round(sp["size"], 1), txt[:50]))
                                break
                        if sp["size"] < 6.0:
                            findings["tiny"].append((pno + 1, round(sp["size"], 1), txt[:50]))
                        if (r.x0 < pr.x0 - 1 or r.y0 < pr.y0 - 1
                                or r.x1 > pr.x1 + 1 or r.y1 > pr.y1 + 1):
                            findings["overflow"].append((pno + 1, txt[:50]))
            findings["pages"].append({
                "page": pno + 1, "spans": nspans, "images": len(imgs),
                "font_mean": round(sum(sizes) / len(sizes), 1) if sizes else 0,
                "font_min": round(min(sizes), 1) if sizes else 0,
            })
    finally:
        d.close()
    return findings
