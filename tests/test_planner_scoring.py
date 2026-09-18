"""Unit test scoring del Planner (pesi e regole legacy, senza Textual)."""

from datetime import date

from src.models import Priority
from src.planner import scoring
from tests.conftest import make_todo

TODAY = "2026-09-10"
TODAY_D = date(2026, 9, 10)


def _score(todo, **kw):
    args = {"today": TODAY_D, "today_s": TODAY, "stale_n": None, "calib": None}
    args.update(kw)
    return scoring.score(todo, **args)


def test_scadenze_e_mandatory():
    s, r, m = _score(make_todo("A", todo_id=1, due="2026-09-09", priority=Priority.LOW))
    assert (s, r, m) == (100, [("plan_overdue", {})], True)
    s, r, m = _score(make_todo("B", todo_id=2, due=TODAY, priority=Priority.HIGH))
    assert (s, r, m) == (80, [("plan_due_today", {}), ("plan_prio", {})], True)
    s, r, m = _score(
        make_todo("C", todo_id=3, due="2026-09-11", priority=Priority.HIGH)
    )
    assert (s, r, m) == (50, [("plan_due_tomorrow", {}), ("plan_prio", {})], False)
    s, r, m = _score(make_todo("D", todo_id=4))
    assert (s, r, m) == (10, [], False)  # priorita' media default, nessun motivo


def test_priorita():
    assert _score(make_todo("H", todo_id=1, priority=Priority.HIGH))[0] == 20
    assert _score(make_todo("H", todo_id=1, priority=Priority.HIGH))[1] == [
        ("plan_prio", {})
    ]
    assert _score(make_todo("M", todo_id=2, priority=Priority.MEDIUM))[0] == 10
    assert _score(make_todo("L", todo_id=3, priority=Priority.LOW))[0] == 0
    assert _score(make_todo("L", todo_id=3, priority=Priority.LOW))[1] == []


def test_stale_e_planned():
    s, r, _m = _score(make_todo("S", todo_id=1), stale_n=9)
    assert s == 10 + 15
    assert ("plan_stale", {"n": 9}) in r
    s, r, _m = _score(make_todo("P", todo_id=2, planned_for=TODAY))
    assert s == 10 + 5
    assert ("plan_planned", {}) in r


def test_calibrated_solo_motivo_su_stimati():
    s, r, _m = _score(make_todo("E", todo_id=1, stima_pomo=2), calib=2.0)
    assert ("plan_calibrated", {"f": "x2.0"}) in r
    assert s == 10  # la calibrazione non cambia il merito
    s, r, _m = _score(make_todo("N", todo_id=2), calib=2.0)
    assert all(k != "plan_calibrated" for k, _p in r)


def test_parse_day_e_stale_days():
    assert scoring.parse_day(TODAY) == TODAY_D
    assert scoring.parse_day("xx") is None
    assert scoring.parse_day("") is None
    assert scoring.stale_days("", [], TODAY_D) is None
    todos = [
        make_todo("Q", todo_id=1, project="q"),
        make_todo(
            "qd", todo_id=2, project="q", done=True, completed_at="2026-09-09 10:00"
        ),
    ]
    assert scoring.stale_days("q", todos, TODAY_D) is None  # completato ieri
    todos = [make_todo("R", todo_id=3, project="r", created="2026-08-01 10:00")]
    assert scoring.stale_days("r", todos, TODAY_D) == 40


def test_rank_key_merito_scadenza_id():
    a = make_todo("A", todo_id=2, due="2026-09-11")
    b = make_todo("B", todo_id=1, due="2026-09-11")
    assert sorted([(a, 10, []), (b, 10, [])], key=scoring.rank_key)[0][0] is b
    c = make_todo("C", todo_id=3)
    assert sorted([(c, 5, []), (a, 10, [])], key=scoring.rank_key)[0][0] is a
