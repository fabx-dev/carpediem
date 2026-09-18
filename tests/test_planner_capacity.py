"""Unit test capacity del Planner (monte-ore e selezione, senza Textual)."""

from src.planner import capacity
from tests.conftest import make_todo

TODAY = "2026-09-10"


def _cand(todo, score=10, reasons=None, mandatory=False):
    return (todo, score, list(reasons or []), mandatory)


def test_total():
    assert capacity.total(6.0) == 12.0
    assert capacity.total(0) == 0.0
    assert capacity.total(-3) == 0.0
    assert capacity.total("x") == 0.0
    assert capacity.total(None) == 0.0


def test_normalize_factor():
    assert capacity.normalize_factor(None) is None
    assert capacity.normalize_factor("xx") is None
    assert capacity.normalize_factor(2.0) == 2.0
    assert capacity.normalize_factor(99.0) == 3.0
    assert capacity.normalize_factor(0.1) == 0.5


def test_estimate():
    t = make_todo("E", todo_id=1, stima_pomo=2)
    assert capacity.estimate(t, None) == 2
    assert capacity.estimate(t, 2.0) == 4
    assert capacity.estimate(make_todo("N", todo_id=2), None) == 1
    assert capacity.estimate(make_todo("N", todo_id=2), 2.0) == 2
    assert capacity.estimate(make_todo("X", todo_id=3), "xx") == 1


def test_allocate_mandatory_mai_tagliati():
    big = make_todo("Big", todo_id=1, due="2026-09-01", stima_pomo=50)
    small = make_todo("S", todo_id=2, stima_pomo=1)
    out = capacity.allocate(
        [_cand(big, 100, [("plan_overdue", {})], True), _cand(small)],
        today_s=TODAY,
        capacity=2.0,
        calib=None,
    )
    assert [t.id for t, _s, _r, _m in out] == [1, 2]
    reasons = {t.id: [k for k, _p in r] for t, _s, r, _m in out}
    assert "plan_cut" not in reasons[1]  # il mandatory sfora ma resta
    assert "plan_cut" in reasons[2]  # gli altri si tagliano sul resto
    mand = {t.id: m for t, _s, _r, m in out}
    assert mand == {1: True, 2: False}


def test_allocate_greedy_e_taglio_in_fondo():
    a = make_todo("A", todo_id=1)
    b = make_todo("B", todo_id=2)
    out = capacity.allocate(
        [_cand(a), _cand(b)], today_s=TODAY, capacity=1.0, calib=None
    )
    assert [t.id for t, _s, _r, _m in out] == [1, 2]
    reasons = {t.id: [k for k, _p in r] for t, _s, r, _m in out}
    assert "plan_cut" not in reasons[1]
    assert "plan_cut" in reasons[2]


def test_allocate_pianificati_sempre_dentro():
    p = make_todo("P", todo_id=1, planned_for=TODAY, stima_pomo=50)
    out = capacity.allocate([_cand(p, 5)], today_s=TODAY, capacity=1.0, calib=None)
    assert [t.id for t, _s, _r, _m in out] == [1]
    assert "plan_cut" not in [k for k, _p in out[0][2]]
