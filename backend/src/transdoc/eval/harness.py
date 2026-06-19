# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Eval harness: run the pipeline over a corpus, score each document, emit a scorecard, and
diff against a saved baseline to gate regressions.

Deterministic by default: engine=echo (no network, no ToS-grey endpoint) so the structure and
rendering metrics are stable run-to-run and CI-able. Translation chrF needs gold references and
a real engine, so it is only computed when a `.ref.<lang>.txt` sidecar exists.

Gold sidecars (optional, next to each input file <stem><ext>):
  <stem>.gold.txt        plain-text ground truth -> CER / WER of the EXTRACTED text
  <stem>.ref.<lang>.txt  reference translation   -> chrF of the TRANSLATED text

Usage:
  python -m transdoc.eval.harness corpus/synthetic
  python -m transdoc.eval.harness corpus/synthetic --out scorecard.json
  python -m transdoc.eval.harness corpus/synthetic --baseline eval_baseline.json   # CI gate
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from ..config import Config, Engine, OutputFormat
from .metrics import cer, chrf, pdf_fidelity, structure_metrics, wer

_DOC_EXTS = {".pdf", ".docx", ".doc", ".odt", ".pptx", ".xlsx", ".epub", ".txt", ".html",
             ".png", ".jpg", ".jpeg", ".tiff", ".srt", ".vtt"}

# Counts that must not shrink and flags/defects that must not grow, vs the baseline.
_NO_SHRINK = ("blocks", "formulas", "tables", "table_cells", "figures")
_NO_GROW = ("flagged", "overwrite", "tiny", "overflow")


def _doc_text(doc) -> str:
    return "\n".join(b.text for b in doc.ordered_blocks() if b.text.strip())


def _out_text(doc) -> str:
    return "\n".join(b.output_text for b in doc.ordered_blocks() if b.output_text.strip())


def score_doc(path: Path, cfg: Config, workdir: Path, structure_only: bool = False) -> dict:
    """Run the pipeline on one file and return its metric row.

    structure_only omits the PDF render-fidelity metrics (overwrite/tiny/overflow). Those depend
    on the rendering platform's fonts + PyMuPDF substitution, so they aren't byte-stable across
    machines and would cause false regressions when a baseline is gated on a different OS than it
    was generated on. Structure counts come straight from parsing and ARE reproducible."""
    from ..pipeline import run

    out = workdir / (path.stem + ".out.pdf")
    res = run(str(path), cfg, out_path=str(out))
    doc = res.doc
    row: dict = {"file": path.name, **structure_metrics(doc)}

    if structure_only:
        # `flagged` counts blocks carrying ANY flag, but the renderer adds run-time flags
        # (text_expansion / illegible / bidi_mixed) whose count isn't stable run-to-run — heavy
        # text-expansion pages (e.g. Bengali) flip a few blocks in and out of the threshold. Drop
        # it so the cross-OS gate only sees parse-deterministic structure.
        row.pop("flagged", None)
    else:
        if out.exists() and out.suffix.lower() == ".pdf":
            fid = pdf_fidelity(str(out))
            row["overwrite"] = len(fid["overwrite"])
            row["tiny"] = len(fid["tiny"])
            row["overflow"] = len(fid["overflow"])

    gold = path.with_suffix(".gold.txt")
    if gold.exists():
        ref = gold.read_text(encoding="utf-8")
        row["cer"] = round(cer(ref, _doc_text(doc)), 4)
        row["wer"] = round(wer(ref, _doc_text(doc)), 4)

    tgt = cfg.target_lang
    refx = path.with_suffix(f".ref.{tgt}.txt")
    if refx.exists():
        row["chrf"] = round(chrf(refx.read_text(encoding="utf-8"), _out_text(doc)), 2)
    return row


def _is_sidecar(name: str) -> bool:
    # gold (.gold.txt) and reference-translation (.ref.<lang>.txt) sidecars are inputs to the
    # metrics, not documents to score — they'd otherwise be picked up by the .txt extension.
    return name.endswith(".gold.txt") or ".ref." in name or ".out." in name


def run_corpus(corpus: Path, cfg: Config, exclude_dirs: tuple[str, ...] = (),
               structure_only: bool = False) -> dict:
    excluded = {d.strip("/") for d in exclude_dirs}

    def _kept(p: Path) -> bool:
        # skip any file whose path crosses an excluded directory name (e.g. OCR-only dirs whose
        # metrics aren't byte-stable across tesseract versions, so they can't be a hard gate)
        return excluded.isdisjoint(part for part in p.relative_to(corpus).parts)

    files = sorted(p for p in corpus.rglob("*")
                   if p.is_file() and p.suffix.lower() in _DOC_EXTS
                   and not _is_sidecar(p.name) and _kept(p))
    rows: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="transdoc_eval_") as td:
        wd = Path(td)
        for f in files:
            try:
                rows.append(score_doc(f, cfg, wd, structure_only=structure_only))
            except Exception as e:  # one bad file shouldn't sink the whole scorecard
                rows.append({"file": f.name, "error": f"{type(e).__name__}: {e}"})
    card = {"engine": cfg.engine.value, "target_lang": cfg.target_lang,
            "docs": {r["file"]: r for r in rows}}
    if structure_only:
        card["structure_only"] = True
    return card


def diff_baseline(baseline: dict, current: dict, chrf_tol: float = 1.0) -> list[str]:
    """Return human-readable regression lines (empty list = no regression)."""
    regress: list[str] = []
    for name, base in baseline.get("docs", {}).items():
        cur = current.get("docs", {}).get(name)
        if cur is None:
            regress.append(f"{name}: missing from current run")
            continue
        if "error" in cur and "error" not in base:
            regress.append(f"{name}: now errors -> {cur['error']}")
            continue
        for k in _NO_SHRINK:
            if k in base and k in cur and cur[k] < base[k]:
                regress.append(f"{name}: {k} {base[k]} -> {cur[k]} (dropped)")
        for k in _NO_GROW:
            if k in base and k in cur and cur[k] > base[k]:
                regress.append(f"{name}: {k} {base[k]} -> {cur[k]} (grew)")
        if base.get("reading_order_monotonic") and cur.get("reading_order_monotonic") is False:
            regress.append(f"{name}: reading order is no longer monotonic")
        if "chrf" in base and "chrf" in cur and cur["chrf"] < base["chrf"] - chrf_tol:
            regress.append(f"{name}: chrf {base['chrf']} -> {cur['chrf']} (dropped)")
    return regress


def _print_scorecard(card: dict) -> None:
    print(f"\nengine={card['engine']}  target={card['target_lang']}")
    print(f"{'file':30} {'blk':>4} {'frm':>4} {'tbl':>4} {'cell':>4} {'fig':>4} "
          f"{'flag':>4} {'ow':>3} {'tiny':>4} {'cer':>6} {'chrf':>6}")
    print("-" * 92)
    for name, r in card["docs"].items():
        if "error" in r:
            print(f"{name[:30]:30} ERROR {r['error'][:50]}")
            continue
        print(f"{name[:30]:30} {r.get('blocks',0):>4} {r.get('formulas',0):>4} "
              f"{r.get('tables',0):>4} {r.get('table_cells',0):>4} {r.get('figures',0):>4} "
              f"{r.get('flagged',0):>4} {r.get('overwrite',0):>3} {r.get('tiny',0):>4} "
              f"{r.get('cer','-')!s:>6} {r.get('chrf','-')!s:>6}")


def main() -> None:
    ap = argparse.ArgumentParser(description="transdoc eval harness")
    ap.add_argument("corpus", help="directory of input documents")
    ap.add_argument("--engine", default="echo", help="translation engine (default echo)")
    ap.add_argument("--target-lang", default="id")
    ap.add_argument("--out", help="write the scorecard JSON here")
    ap.add_argument("--baseline", help="diff against this scorecard JSON; exit 1 on regression")
    ap.add_argument("--exclude-dir", action="append", default=[],
                    help="directory name to skip (repeatable); e.g. OCR-only dirs whose metrics "
                         "aren't byte-stable across tesseract versions")
    ap.add_argument("--structure-only", action="store_true",
                    help="gate parse-derived structure only (blocks/tables/cells/figures/reading "
                         "order); skip font/platform-sensitive PDF render-fidelity metrics")
    args = ap.parse_args()

    cfg = Config(target_lang=args.target_lang, engine=Engine(args.engine),
                 output_format=OutputFormat.PDF)
    card = run_corpus(Path(args.corpus), cfg, exclude_dirs=tuple(args.exclude_dir),
                      structure_only=args.structure_only)
    _print_scorecard(card)

    if args.out:
        Path(args.out).write_text(json.dumps(card, indent=2), encoding="utf-8")
        print(f"\nwrote {args.out}")

    if args.baseline:
        base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
        regress = diff_baseline(base, card)
        if regress:
            print(f"\nREGRESSION ({len(regress)}):")
            for line in regress:
                print(f"  - {line}")
            sys.exit(1)
        print("\nno regression vs baseline ✓")


if __name__ == "__main__":
    main()
