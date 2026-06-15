"""Tesseract OCR — CPU fallback, always available.

Groups word-level boxes into line/paragraph blocks, carries OCR confidence so the QA
phase can flag low-confidence spans. Weak on Indic/complex scripts — prefer Surya there.
"""

from __future__ import annotations

import functools
import io

from ..config import Config
from ..ir import BBox, Block, BlockType, Confidence, Style
from .base import TESS_LANG


@functools.lru_cache(maxsize=1)
def _avail_langs() -> frozenset[str]:
    """Installed tesseract language + script packs. Parses `--list-langs` directly instead of
    pytesseract.get_languages(), which drops the first-sorted entry — silently hiding the
    uppercase 'Latin' script model (it sorts before lowercase packs)."""
    import subprocess

    import pytesseract
    try:
        out = subprocess.run([pytesseract.pytesseract.tesseract_cmd, "--list-langs"],
                             capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return frozenset()
    # first line is the "List of available languages ..." header; each lang is its own token
    return frozenset(ln.strip() for ln in out.splitlines()[1:]
                     if ln.strip() and " " not in ln.strip())


def _resolve(name: str | None, avail: set) -> str | None:
    """Map a logical pack name to the installed tesseract token. Script models install as
    'script/Latin' via the apt pack but as bare 'Latin' when dropped straight into tessdata/ —
    accept either. Language packs (ell/hin/...) only ever match the bare form."""
    if not name:
        return None
    for cand in (f"script/{name}", name):
        if cand in avail:
            return cand
    return None

# Tesseract OSD script name -> tesseract language pack. Used when the source language is auto:
# without this a non-Latin scan is OCR'd with "eng" and comes back as Latin gibberish.
_SCRIPT_LANG = {
    # Latin pages: the script/Latin model reads every Latin language's diacritics (ç/ã/â/é/...)
    # without guessing the language — "eng" alone drops them (portuguese CER 2.96% -> 0.04% with
    # Latin, eval finding). Falls back to "eng" when the Latin pack isn't installed.
    "Latin": "Latin",
    "Devanagari": "hin", "Han": "chi_sim", "HanS": "chi_sim", "HanT": "chi_tra",
    "Hangul": "kor", "Japanese": "jpn", "Hiragana": "jpn", "Katakana": "jpn",
    "Arabic": "ara", "Cyrillic": "rus", "Hebrew": "heb", "Greek": "ell",
    "Bengali": "ben", "Tamil": "tam", "Telugu": "tel", "Thai": "tha",
    "Kannada": "kan", "Malayalam": "mal", "Gujarati": "guj", "Gurmukhi": "pan",
    "Oriya": "ori", "Sinhala": "sin",
}


class TesseractOCR:
    name = "tesseract"

    def _detect_script_lang(self, image, avail: set) -> str | None:
        """Source=auto: ask Tesseract OSD which SCRIPT the page uses and map it to a lang pack,
        so a Devanagari/Han/Arabic scan isn't read as English. None if undetectable/uninstalled."""
        import re

        import pytesseract
        try:
            osd = pytesseract.image_to_osd(image)
        except Exception:
            return None
        m = re.search(r"Script:\s*([\w]+)", osd)
        code = _SCRIPT_LANG.get(m.group(1)) if m else None
        return code if _resolve(code, avail) else None   # logical name; _langs resolves the token

    def _langs(self, cfg: Config, detected: str | None = None) -> str:
        avail = set(_avail_langs())
        wanted: list[str] = []
        if cfg.source_lang and cfg.source_lang != "auto":
            wanted.append(TESS_LANG.get(cfg.source_lang, cfg.source_lang))
        elif detected:                       # auto source -> OSD-detected script pack
            wanted.append(detected)
        # Add English only as a genuine fallback (Latin / unknown). Adding "eng" to a non-Latin
        # script pack makes tesseract misread native glyphs as Latin lookalikes — Greek ΚΑΙ comes
        # back as Latin "KAI" (eval finding). The script pack already handles digits/punctuation.
        primary = wanted[0] if wanted else None
        if primary is None or primary == "eng":
            wanted.append("eng")
        # resolve each to its installed token (Latin -> script/Latin where present), dedupe
        seen, out = set(), []
        for w in wanted:
            tok = _resolve(w, avail)
            if tok and tok not in seen:
                seen.add(tok)
                out.append(tok)
        return "+".join(out) or "eng"

    def recognize_image_bytes(self, img: bytes, cfg: Config, page: int = 0) -> list[Block]:
        import pytesseract
        from PIL import Image

        image = Image.open(io.BytesIO(img))
        detected = None
        if not cfg.source_lang or cfg.source_lang == "auto":
            detected = self._detect_script_lang(image, set(_avail_langs()))
        lang = self._langs(cfg, detected)
        data = pytesseract.image_to_data(image, lang=lang,
                                         output_type=pytesseract.Output.DICT)

        # Group words by (block_num, par_num, line_num) into paragraph blocks.
        paras: dict[tuple, dict] = {}
        n = len(data["text"])
        for i in range(n):
            txt = data["text"][i].strip()
            if not txt:
                continue
            conf = float(data["conf"][i])
            if conf < 0:
                continue
            key = (data["block_num"][i], data["par_num"][i])
            x, y, w, h = (data["left"][i], data["top"][i],
                          data["width"][i], data["height"][i])
            p = paras.setdefault(key, {"words": [], "confs": [],
                                       "x0": 1e9, "y0": 1e9, "x1": 0, "y1": 0})
            p["words"].append(txt)
            p["confs"].append(conf / 100.0)
            p["x0"], p["y0"] = min(p["x0"], x), min(p["y0"], y)
            p["x1"], p["y1"] = max(p["x1"], x + w), max(p["y1"], y + h)

        blocks: list[Block] = []
        for idx, (key, p) in enumerate(sorted(paras.items())):
            text = " ".join(p["words"])
            avg_conf = sum(p["confs"]) / len(p["confs"])
            blk = Block(
                id=f"p{page}-ocr{idx}",
                type=BlockType.PARAGRAPH,
                page=page,
                text=text,
                bbox=BBox(x0=p["x0"], y0=p["y0"], x1=p["x1"], y1=p["y1"]),
                style=Style(),
                confidence=Confidence(source="ocr", ocr=round(avg_conf, 3)),
            )
            if avg_conf < cfg.flag_threshold:
                blk.flags["low_ocr_confidence"] = f"{avg_conf:.0%}"
            blocks.append(blk)
        return blocks
