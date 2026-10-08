"""Unit test constraints del Planner (ammissibilita', senza Textual)."""

from carpediem.planner import constraints
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
    assert [(t.id, r, m) for t, _s, r, m in skipped] == [
        (2, [("plan_due_today", {}), ("plan_skipped", {})], True)
    ]
    # input non mutato (motivo aggiunto su copia)
    assert scored[1][2] == [("plan_due_today", {})]


def test_eligibility_of_tre_vie():
    """V1 (P4-2): H1/H2 -> EXCLUDED, H3 -> SKIPPED, resto -> ELIGIBLE."""
    assert constraints.eligibility_of(make_todo("A", todo_id=1), TODAY) == (
        constraints.ELIGIBLE
    )
    assert constraints.eligibility_of(
        make_todo("S", todo_id=2, plan_skip=TODAY), TODAY
    ) == (constraints.SKIPPED)
    done = make_todo("D", todo_id=3)
    done.done = True
    assert constraints.eligibility_of(done, TODAY) == constraints.EXCLUDED
    paused = make_todo("P", todo_id=4)
    paused.paused = True
    assert constraints.eligibility_of(paused, TODAY) == constraints.EXCLUDED
    assert constraints.eligibility_of(make_todo("N", todo_id=None), TODAY) == (
        constraints.EXCLUDED
    )
    # Costanti frozen come gli stati decisione.
    assert {constraints.ELIGIBLE, constraints.SKIPPED, constraints.EXCLUDED} == {
        "eligible",
        "skipped",
        "excluded",
    }
