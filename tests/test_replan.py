"""Replanning Engine M4: proposta esplicita e deterministica, mai commit.

Input: piano corrente (planned_for), ora corrente, rimanenti, calendario
(busy), capacita'. Output: ReplanProposal con kept/moved/dropped/added +
motivi reali. Puro: non muta i todos, non scrive.
"""

from datetime import date, datetime

from src.planner.models import TimeWindow
from src.planner.replan import ADDED, DROPPED, KEPT, MOVED, replan
from tests.conftest import make_todo

TODAY = "2026-09-10"


def _avail(h1=9, m1=0, h2=18, m2=0):
    return [TimeWindow(datetime(2026, 9, 10, h1, m1), datetime(2026, 9, 10, h2, m2))]


def _at(h, m=0):
    return datetime(2026, 9, 10, h, m)


def test_completati_esclusi_e_capacita_riusata():
    todos = [
        make_todo("A", todo_id=1, planned_for=TODAY, stima_pomo=2),
        make_todo("B", todo_id=2, planned_for=TODAY, stima_pomo=2),
        make_todo("C", todo_id=3, stima_pomo=1),
    ]
    todos[1].done = True
    todos[1].completed_at = TODAY + " 10:00"
    before = [(t.id, t.planned_for) for t in todos]
    p = replan(todos, TODAY, 6.0, _avail(), now=_at(9))
    kinds = {m.todo_id: m.kind for m in p.moves}
    assert 2 not in kinds  # completato: fuori dal replan
    assert kinds[1] in (KEPT, MOVED) and kinds[3] == ADDED
    assert [(t.id, t.planned_for) for t in todos] == before  # puro
    assert p.residual_pomo == p.capacity_pomo - p.planned_pomo


def test_slot_passati_indisponibili():
    todos = [make_todo("A", todo_id=1, planned_for=TODAY, stima_pomo=2)]
    p = replan(todos, TODAY, 6.0, _avail(), now=_at(15))
    assert [(m.kind, m.new_start) for m in p.moves] == [(MOVED, "15:00")]
    assert p.moves[0].new_end == "16:00"


def test_mandatory_resta_e_unschedulable_fuori_slot():
    todos = [make_todo("M", todo_id=1, due="2026-09-01", stima_pomo=4)]
    p = replan(todos, TODAY, 6.0, _avail(9, 0, 10, 0), now=_at(9))
    assert [(m.kind, m.new_start) for m in p.moves] == [(ADDED, None)]


def test_busy_sposta_dopo_evento():
    todos = [make_todo("A", todo_id=1, planned_for=TODAY, stima_pomo=2)]
    busy = [TimeWindow(_at(9), _at(12))]
    p = replan(todos, TODAY, 6.0, _avail(), busy, now=_at(9))
    assert [(m.kind, m.new_start) for m in p.moves] == [(MOVED, "12:00")]


def test_dropped_con_motivo_reale():
    # Unico caso reale di drop: task pianificato ma skippato oggi
    # (partition rispetta lo skip anche sui pianificati).
    todos = [
        make_todo("A", todo_id=1, planned_for=TODAY),
        make_todo("B", todo_id=2, planned_for=TODAY, plan_skip=TODAY),
    ]
    p = replan(todos, TODAY, 6.0, _avail(), now=_at(9))
    by_id = {m.todo_id: m for m in p.moves}
    assert by_id[1].kind in (KEPT, MOVED)
    assert by_id[2].kind == DROPPED
    assert by_id[2].primary == ("plan_skipped", {})
    assert by_id[2].new_start is None


def test_senza_finestra_solo_decisioni():
    todos = [make_todo("A", todo_id=1, planned_for=TODAY, stima_pomo=2)]
    p = replan(todos, TODAY, 6.0, [], now=_at(9))
    assert [(m.kind, m.new_start) for m in p.moves] == [(KEPT, None)]
    assert p.residual_pomo == p.capacity_pomo - p.planned_pomo


def test_determinismo_e_ordine():
    todos = [
        make_todo("A", todo_id=1, planned_for=TODAY, stima_pomo=2),
        make_todo("B", todo_id=2, stima_pomo=8),
        make_todo("C", todo_id=3, planned_for=TODAY, stima_pomo=1),
    ]
    p1 = replan(todos, TODAY, 6.0, _avail(), now=_at(10))
    p2 = replan(todos, TODAY, 6.0, _avail(), now=_at(10))
    assert p1 == p2
    kinds = [m.kind for m in p1.moves]
    assert kinds == sorted(
        kinds, key=lambda k: ("kept", "moved", "added", "dropped").index(k)
    )


def test_pianificati_mai_dropped_privilegio():
    # capacity.allocate non taglia mai i planned_for==oggi: il replan
    # non fa perdere il piano a chi ce l'ha (solo gli slot cambiano).
    todos = [make_todo(f"T{i}", todo_id=i, planned_for=TODAY) for i in range(1, 5)]
    p = replan(todos, TODAY, 0.5, _avail(), now=_at(9))
    assert all(m.kind in (KEPT, MOVED) for m in p.moves)
    assert {m.todo_id for m in p.moves} == {1, 2, 3, 4}


def test_apply_replan_conteggi_e_skip():
    import src.domain as domain
    from src.planner.replan import ReplanMove, ReplanProposal

    todos = [
        make_todo("A", todo_id=1, planned_for=TODAY),
        make_todo("B", todo_id=2, planned_for=TODAY),
        make_todo("C", todo_id=3, plan_skip="2026-09-01"),
        make_todo("D", todo_id=4, planned_for=TODAY),
    ]
    todos[3].paused = True  # inattivo: mai toccato
    proposal = ReplanProposal(
        date(2026, 9, 10),
        now=_at(9),
        moves=(
            ReplanMove(1, KEPT),
            ReplanMove(2, DROPPED, primary=("plan_cut", {})),
            ReplanMove(3, ADDED),
            ReplanMove(4, DROPPED),
            ReplanMove(99, ADDED),
        ),
    )
    added, dropped = domain.apply_replan(todos, proposal, TODAY)
    assert (added, dropped) == (1, 1)
    by_id = {t.id: t for t in todos}
    assert by_id[1].planned_for == TODAY  # kept invariato
    assert by_id[2].planned_for == "" and by_id[2].plan_skip == TODAY
    assert by_id[3].planned_for == TODAY and by_id[3].plan_skip == ""
    assert by_id[4].planned_for == TODAY  # sospeso: intoccato
    assert domain.apply_replan(todos, None, TODAY) == (0, 0)


def test_move_kinds_costanti():
    import sys

    assert (KEPT, MOVED, DROPPED, ADDED) == ("kept", "moved", "dropped", "added")
    mod = sys.modules["src.planner.replan"]
    assert set(mod._KIND_ORDER) == {KEPT, MOVED, DROPPED, ADDED}
