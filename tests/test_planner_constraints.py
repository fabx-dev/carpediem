"""Unit test constraints del Planner (ammissibilita', senza Textual)."""

from src.planner import constraints
from tests.conftest import make_todo

TODAY = "2026-09-10"


def test_is_eligible():
    assert constraints.is_eligible(make_todo("A", todo_id=1))
    assert not constraints.is_eligible(make_todo("D", todo_id=1, done=True))
    assert not constraints.is_eligible(make_todo("P", todo_id=2, paused=True))
    assert not constraints.is_eligible(make_todo("N", todo_id=None))


def test_is_skipped():
    assert constraints.is_skipped(make_todo("S", todo_id=1, plan_skip=TODAY), TODAY)
    assert not constraints.is_skipped(
        make_todo("S", todo_id=1, plan_skip="2026-09-09"), TODAY
    )
    assert not constraints.is_skipped(make_todo("A", todo_id=2), TODAY)


def test_partition_gruppi_motivo_ordine():
    scored = [
        (make_todo("A", todo_id=1, due=TODAY), 60, [("plan_due_today", {})], True),
        (
            make_todo("S", todo_id=2, due=TODAY, stima_pomo=50, plan_skip=TODAY),
            60,
            [("plan_due_today", {})],
            True,
        ),
        (make_todo("B", todo_id=3, due="2026-09-11"), 30, [], False),
    ]
    cands, skipped = constraints.partition(scored, TODAY)
    assert [t.id for t, _s, _r, _m in cands] == [1, 3]
    assert [(t.id, r) for t, _s, r in skipped] == [
        (2, [("plan_due_today", {}), ("plan_skipped", {})])
    ]
    # input non mutato (motivo aggiunto su copia)
    assert scored[1][2] == [("plan_due_today", {})]
