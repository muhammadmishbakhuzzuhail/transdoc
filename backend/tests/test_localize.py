# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Locale number formatting (cfg.localize): comma-decimal targets get 1,234.56 -> 1.234,56,
dot-decimal targets are untouched, and version numbers / dates are left alone."""

from __future__ import annotations

from transdoc.translate.localize import localize_numbers


def test_comma_decimal_target():
    assert localize_numbers("Total 1,234.56 and 99.50", "id") == "Total 1.234,56 and 99,50"
    assert localize_numbers("price 1234.5", "de") == "price 1234,5"


def test_dot_decimal_target_untouched():
    assert localize_numbers("Total 1,234.56", "en") == "Total 1,234.56"
    assert localize_numbers("Total 1,234.56", "ja") == "Total 1,234.56"


def test_versions_and_dates_safe():
    # dotted version runs and numeric dates must not be reinterpreted as decimals
    assert localize_numbers("version 1.2.3 build 4.5.6", "id") == "version 1.2.3 build 4.5.6"
    assert localize_numbers("on 12.31.2025 today", "id") == "on 12.31.2025 today"
