"""Translation-quality gate: scoring aggregation + regression check (offline, engine stubbed)."""

from __future__ import annotations

from transdoc.eval.quality_gate import check_regression, load_set, score_set


def test_set_loads_and_is_well_formed():
    items = load_set()
    assert len(items) >= 5
    for it in items:
        assert it["src"] and it["ref"] and it["src_lang"] and it["tgt_lang"]


def test_score_set_perfect_when_engine_echoes_reference():
    items = [
        {"src_lang": "en", "tgt_lang": "id", "src": "a", "ref": "halo dunia"},
        {"src_lang": "en", "tgt_lang": "id", "src": "b", "ref": "selamat pagi"},
    ]
    # stub "engine" returns the reference verbatim -> chrF 100
    refs = {g["src"]: g["ref"] for g in items}

    def translate(srcs, sl, tl):
        return [refs[s] for s in srcs]

    r = score_set(items, translate)
    assert r["overall"] == 100.0
    assert r["pairs"]["en-id"] == 100.0
    assert r["n"] == 2


def test_score_set_groups_by_pair():
    items = [
        {"src_lang": "en", "tgt_lang": "id", "src": "x", "ref": "satu"},
        {"src_lang": "en", "tgt_lang": "de", "src": "y", "ref": "eins"},
    ]
    r = score_set(items, lambda srcs, sl, tl: ["zzz" for _ in srcs])
    assert set(r["pairs"]) == {"en-id", "en-de"}


def test_check_regression_detects_drop_and_missing():
    baseline = {"pairs": {"en-id": 55.0, "en-de": 50.0}, "overall": 52.5}
    current = {"pairs": {"en-id": 52.0}, "overall": 52.0}     # en-id -3, en-de missing
    msgs = check_regression(current, baseline, tol=2.0)
    assert any("en-id" in m for m in msgs)        # 52 < 55 - 2
    assert any("en-de" in m and "missing" in m for m in msgs)


def test_check_regression_within_tolerance_is_clean():
    baseline = {"pairs": {"en-id": 55.0}, "overall": 55.0}
    current = {"pairs": {"en-id": 54.0}, "overall": 54.0}     # within tol 2.0
    assert check_regression(current, baseline, tol=2.0) == []
