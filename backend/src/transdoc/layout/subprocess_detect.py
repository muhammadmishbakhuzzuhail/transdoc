# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Run PP-DocLayout in a SEPARATE interpreter and write the regions as JSON.

paddlepaddle-gpu and torch cannot share one venv (their nvidia-nccl wheels collide), so the
main app keeps torch and delegates layout detection to an isolated paddle venv via this script:

    <paddle-python> -m transdoc.layout.subprocess_detect <pdf> <out.json> <pno> [<pno> ...]

Results are written to ``out.json`` (NOT stdout) as ``{pno: [[label,x0,y0,x1,y1], ...]}`` so
paddle's own stdout chatter can't corrupt the payload. See the paddle-torch-venv-conflict note.
"""

from __future__ import annotations

import json
import sys


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        sys.stderr.write("usage: subprocess_detect <pdf> <out.json> <pno> [<pno> ...]\n")
        return 2
    pdf_path, out_path = argv[0], argv[1]
    pnos = [int(x) for x in argv[2:]]

    import fitz

    from transdoc.layout.paddle_layout import PaddleLayoutDetector

    det = PaddleLayoutDetector()
    doc = fitz.open(pdf_path)
    try:
        result = {
            pno: [[r.label, r.x0, r.y0, r.x1, r.y1] for r in det.detect(doc[pno])]
            for pno in pnos
        }
    finally:
        doc.close()
    with open(out_path, "w") as fh:
        json.dump(result, fh)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
