# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Text-expansion fidelity eval (Area C).

Translations run longer than the source — DE/FI/RU expand ~30%, and a verbose register more. The
positioned PDF reconstruction must absorb that without illegibly shrinking text or clipping it off
the page. This eval measures how well it does, deterministically and offline: it extracts each
source PDF, SIMULATES expansion by padding every translatable block by a fixed factor (no network,
no engine), renders through ``render_reconstruct``, then scores the output —

  illegible : blocks the renderer flagged below the 6pt readable floor (shrink failed)
  shrunk    : blocks flagged 'text_expansion' (shrunk 60-100% — legible but tight)
  tiny      : output spans rendered < 6pt (PyMuPDF geometry audit, independent of our flags)
  overflow  : output spans whose bbox leaves the page rect (clipped text)
  spill     : extra pages added so expanded content stayed full-size (the reflow working)

Lower illegible/tiny/overflow is better; `spill` is the reflow doing its job, not a regression.
Bring your own corpus (PDFs with a real text layer), like the other real-corpus evals:

    cd backend && .venv/bin/python -m scripts.eval_expansion corpus/real/**/*.pdf
    cd backend && .venv/bin/python -m scripts.eval_expansion --factor 1.5 --baseline exp.json doc.pdf

With --baseline, the run is compared to a saved JSON and exits non-zero if illegible/tiny/overflow
rose (a regression gate); without it, --out writes the current totals as a new baseline.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _expand(text: str, factor: float) -> str:
    """Deterministically pad text to ~factor× its length, simulating target-language expansion.
    Repeats the source words (keeps script/!width characteristics) — no randomness, no network."""
    if factor <= 1.0 or not text.strip():
        return text
    words = text.split()
    if not words:
        return text
    extra = int(len(words) * (factor - 1.0))
    pad = [words[i % len(words)] for i in range(extra)]
    return " ".join(words + pad)


def _render_expanded(path: str, factor: float) -> dict:
    """Extract -> simulate expansion -> reconstruct; return per-doc expansion metrics."""
    import tempfile

    import fitz

    from transdoc.config import Config, OutputFormat
    from transdoc.extract import extract
    from transdoc.ingest.detect import detect
    from transdoc.ir import BlockType
    from transdoc.regenerate.pdf_out import render_reconstruct

    cfg = Config(target_lang="id", output_format=OutputFormat.PDF)
    doc = extract(detect(path), cfg)
    for b in doc.blocks:
        if b.is_translatable:
            b.translated = _expand(b.text, factor)
        elif b.type == BlockType.TABLE and b.table:
            for row in b.table.rows:
                for c in row:
                    if c.text.strip():
                        c.translated = _expand(c.text, factor)

    pages_in = doc.page_count or 1
    out = Path(tempfile.mkdtemp()) / "expanded.pdf"
    render_reconstruct(doc, cfg, str(out))
    pages_out = fitz.open(str(out)).page_count

    illegible = sum(1 for b in doc.blocks if "illegible" in b.flags)
    shrunk = sum(1 for b in doc.blocks if "text_expansion" in b.flags)

    from transdoc.eval.metrics import pdf_fidelity
    audit = pdf_fidelity(str(out))
    return {
        "blocks": len([b for b in doc.blocks if b.is_translatable]),
        "illegible": illegible,
        "shrunk": shrunk,
        "tiny": len(audit["tiny"]),
        "overflow": len(audit["overflow"]),
        "pages_in": pages_in,
        "pages_out": pages_out,
        "spill": max(0, pages_out - pages_in),
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="text-expansion fidelity eval (Area C)")
    ap.add_argument("docs", nargs="+", help="source PDF(s) with a real text layer")
    ap.add_argument("--factor", type=float, default=1.4,
                    help="simulated expansion factor (default 1.4 ~ German)")
    ap.add_argument("--baseline", help="compare against this JSON; exit non-zero on regression")
    ap.add_argument("--out", help="write the run totals to this JSON (new baseline)")
    args = ap.parse_args(argv)

    hdr = f"{'file':30} {'blk':>4} {'illeg':>6} {'shrunk':>7} {'tiny':>5} {'ovfl':>5} {'spill':>6}"
    print(hdr)
    print("-" * len(hdr))
    totals = {"blocks": 0, "illegible": 0, "shrunk": 0, "tiny": 0, "overflow": 0, "spill": 0}
    for path in args.docs:
        try:
            m = _render_expanded(path, args.factor)
        except Exception as e:
            print(f"{Path(path).name[:30]:30} ERROR {type(e).__name__}: {e}")
            continue
        for k in totals:
            totals[k] += m[k]
        print(f"{Path(path).name[:30]:30} {m['blocks']:>4} {m['illegible']:>6} {m['shrunk']:>7} "
              f"{m['tiny']:>5} {m['overflow']:>5} {m['spill']:>6}")
    print("-" * len(hdr))
    print(f"{'TOTAL':30} {totals['blocks']:>4} {totals['illegible']:>6} {totals['shrunk']:>7} "
          f"{totals['tiny']:>5} {totals['overflow']:>5} {totals['spill']:>6}")

    if args.out:
        Path(args.out).write_text(json.dumps(totals, indent=2))
        print(f"\nwrote baseline -> {args.out}")
    if args.baseline:
        base = json.loads(Path(args.baseline).read_text())
        regressed = [k for k in ("illegible", "tiny", "overflow")
                     if totals[k] > base.get(k, 0)]
        if regressed:
            print(f"\nREGRESSION in {', '.join(regressed)} vs baseline {args.baseline}")
            return 1
        print(f"\nno regression vs baseline {args.baseline}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
