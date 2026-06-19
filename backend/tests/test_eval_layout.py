# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Layout region-match metric (IoU + detection P/R/F1 + label accuracy)."""

from __future__ import annotations

from transdoc.eval.metrics import bbox_iou, layout_match

_REFS = [("paragraph", (0, 0, 100, 50)), ("table", (0, 60, 100, 120))]


def test_bbox_iou():
    assert bbox_iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert bbox_iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    assert bbox_iou((0, 0, 10, 10), (0, 0, 10, 5)) == 0.5   # half overlap


def test_perfect_match():
    m = layout_match(_REFS, _REFS)
    assert m["mean_iou"] == 1.0 and m["f1"] == 1.0 and m["label_acc"] == 1.0


def test_wrong_label_drops_label_acc_not_iou():
    hyps = [("paragraph", (2, 2, 100, 52)), ("figure", (0, 60, 100, 120))]  # table->figure
    m = layout_match(_REFS, hyps)
    assert m["f1"] == 1.0                 # boxes still matched
    assert m["label_acc"] == 0.5          # one mislabelled
    assert m["mean_iou"] < 1.0            # slight drift


def test_missing_and_extra_drop_f1():
    hyps = [("paragraph", (0, 0, 100, 50)), ("x", (500, 500, 600, 600))]   # 1 hit, 1 spurious
    m = layout_match(_REFS, hyps)
    assert m["precision"] == 0.5 and m["recall"] == 0.5 and m["f1"] == 0.5


def test_empty_both_is_one():
    m = layout_match([], [])
    assert m["mean_iou"] == 1.0 and m["f1"] == 1.0
