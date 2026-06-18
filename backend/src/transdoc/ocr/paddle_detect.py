"""PaddleOCR worker — runs inside the isolated layout_venv.

paddlepaddle and torch collide (nccl) in one process, so when paddleocr isn't importable in the
main env, ocr/paddle.py shells out to this module in the paddle venv. It reads one image and
writes the recognized lines (text + score + polygon) as JSON. Invoked as:

    <layout_venv>/bin/python -m transdoc.ocr.paddle_detect <image_path> <out_json> [lang]
"""

from __future__ import annotations

import json
import os
import sys

# Disable paddle's oneDNN/mkldnn CPU kernels: they raise
# NotImplementedError(ConvertPirAttribute2RuntimeAttribute) on this build's CPU path. This only
# affects the CPU code path — on a GPU it's a no-op — so device stays auto (GPU when available,
# plain CPU otherwise) and the CPU fallback no longer crashes.
os.environ.setdefault("FLAGS_use_mkldnn", "0")


def _make_ocr(lang: str):
    from paddleocr import PaddleOCR
    kw = dict(use_doc_orientation_classify=False, use_doc_unwarping=False,
              use_textline_orientation=False, enable_mkldnn=False)
    try:
        return PaddleOCR(lang=lang, **kw)
    except Exception:
        return PaddleOCR(lang="en", **kw)        # unknown model -> still produce output


def main() -> int:
    img_path, out_path = sys.argv[1], sys.argv[2]
    lang = sys.argv[3] if len(sys.argv) > 3 else "en"

    import numpy as np
    from PIL import Image

    arr = np.array(Image.open(img_path).convert("RGB"))
    result = _make_ocr(lang).predict(arr)

    items = []
    for r in result:
        for text, score, poly in zip(r["rec_texts"], r["rec_scores"], r["rec_polys"]):
            items.append({"text": text, "score": float(score),
                          "poly": [[float(p[0]), float(p[1])] for p in poly]})
    with open(out_path, "w") as fh:
        json.dump(items, fh)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
