"""Locale-aware number formatting (opt-in via cfg.localize).

Many target languages write decimals with a comma and group thousands with a dot/space
(1,234.56 -> 1.234,56). This converts plain numbers in the translated text to the target's
convention. It runs on the translated string *before* placeholder restore, so numbers that
were protected verbatim (currency-with-unit, dates, codes) are still [PH] tags and are left
untouched. Scope is deliberately narrow: only the decimal/thousands separators, not date
order, units, or currency symbols.
"""

from __future__ import annotations

import re

# Target languages (ISO 639-1) that use a comma decimal separator.
_COMMA_DECIMAL = {
    "id", "de", "es", "fr", "it", "pt", "nl", "ru", "tr", "pl", "uk", "cs", "da",
    "fi", "sv", "nb", "no", "ro", "hu", "el", "vi", "hr", "sk", "sl", "lt", "lv", "et",
}

# US-grouped number: 1,234 or 1,234.56  (needs at least one thousands group)
_US_GROUPED = re.compile(r"(?<![\d.,])\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\d.,])")
# Plain decimal: 1234.56  (not a version run, and not the mantissa of scientific notation —
# "1.5e-10" must not become "1,5e-10")
_PLAIN_DECIMAL = re.compile(r"(?<![\d.,])\d+\.\d+(?![\d.,eE])")


def localize_numbers(text: str, target: str | None) -> str:
    lang = (target or "").lower().split("-")[0]
    if lang not in _COMMA_DECIMAL or not text:
        return text

    def _swap(m: re.Match) -> str:           # 1,234.56 -> 1.234,56
        return m.group(0).replace(",", "\0").replace(".", ",").replace("\0", ".")

    text = _US_GROUPED.sub(_swap, text)
    text = _PLAIN_DECIMAL.sub(lambda m: m.group(0).replace(".", ","), text)
    return text
