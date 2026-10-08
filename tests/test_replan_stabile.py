"""F4 replan stabile: KEPT preciso, churn minimo, capacita' vs tempo."""

from datetime import datetime

from carpediem.planner.models import PlanItem, ScheduledItem, TimeWindow
from carpediem.planner.replan import (
    ADDED,
    DROPPED,
    KEPT,
    MOVED,
    _is_kept,
    replan,
)
from tests.conftest import make_todo

TODAY = "2026-10-08"


def at(h, m=0):
    return datetime(2026, 10, 8, h, m)


def avail(h1=9, h2=18):
    return [TimeWindow(at(h1), at(h2))]


def kinds(p):
    return {m.todo_id: m.kind for m in p.moves}


def test_kept_quando_nulla_cambia():
    todos = [
        make_todo("A", todo_id=1, planned_for=TODAY, stima_pomo=2),
        make_todo("B", todo_id=2, planned_for=TODAY, stima_pomo=2),
        make_todo("C", todo_id=3, stima_pomo=1),
    ]
    from carpediem.screens.plan import scheduled_for_today

    sched, _, _, _, _ = scheduled_for_today(
        todos,
        TODAY,
        6.0,
        {"date": TODAY, "start": "09:00", "end": "18:00"},
        now=at(9),
    )
    p = replan(todos, TODAY, 6.0, avail(), now=at(9), current=sched)
    assert kinds(p) == {1: KEPT, 2: KEPT, 3: ADDED}
    # Idempotente: stesso now, stesso risultato.
    again = replan(todos, TODAY, 6.0, avail(), now=at(9), current=sched)
    assert [(m.todo_id, m.kind, m.new_start) for m in again.moves] == [
        (m.todo_id, m.kind, m.new_start) for m in p.moves
    ]


def test_moved_solo_se_costretto_dal_busy():
    todos = [
        make_todo("A", todo_id=1, planned_for=TODAY, stima_pomo=2),
        make_todo("B", todo_id=2, planned_for=TODAY, stima_pomo=2),
    ]
    from carpediem.screens.plan import scheduled_for_today

    window = {"date": TODAY, "start": "09:00", "end": "18:00"}
    sched, _, _, _, _ = scheduled_for_today(todos, TODAY, 6.0, window, now=at(9))
    # Il busy copre lo slot di A (09:00-10:00): A si sposta per forza
    # (la cascata su B e' spostamento costretto, non churn gratuito).
    busy = [TimeWindow(at(9), at(10))]
    p = replan(todos, TODAY, 6.0, avail(), busy, now=at(9), current=sched)
    assert kinds(p)[1] == MOVED
    moved_b = next(m for m in p.moves if m.todo_id == 2)
    assert moved_b.new_start is not None  # B resta collocato, non perde lo slot
    # Busy in coda vuota (17:00-18:00, task finiti per le 11:00): tutto KEPT.
    calm = replan(
        todos,
        TODAY,
        6.0,
        avail(),
        [TimeWindow(at(17), at(18))],
        now=at(9),
        current=sched,
    )
    assert kinds(calm) == {1: KEPT, 2: KEPT}


def test_nuovo_task_non_ruba_lo_slot_al_confermato():
    """Due passaggi: il confermato sceglie prima, l'aggiunto riempie dopo."""
    todos = [
        make_todo("A", todo_id=1, planned_for=TODAY, stima_pomo=2),
        make_todo("Z", todo_id=9, stima_pomo=2),
    ]
    from carpediem.screens.plan import scheduled_for_today

    window = {"date": TODAY, "start": "09:00", "end": "18:00"}
    sched, _, _, _, _ = scheduled_for_today(todos, TODAY, 6.0, window, now=at(9))
    old_a = next(s for s in sched.scheduled if s.item.todo_id == 1)
    p = replan(todos, TODAY, 6.0, avail(), now=at(9), current=sched)
    assert kinds(p) == {1: KEPT, 9: ADDED}
    new_a = next(m for m in p.moves if m.todo_id == 1)
    assert (new_a.new_start, new_a.new_end) == (
        old_a.start.strftime("%H:%M"),
        old_a.end.strftime("%H:%M"),
    )


def test_is_kept_slot_parzialmente_trascorso_mai():
    """Atomici: 10:00-11:00 con now 10:30 non e' KEPT anche se identico."""
    slot = ScheduledItem(PlanItem(1, 0, (), 2, False), at(10), at(11))
    same = ScheduledItem(PlanItem(1, 0, (), 2, False), at(10), at(11))
    assert _is_kept(slot, same, at(10, 30)) is False
    assert _is_kept(slot, same, at(10)) is True
    assert _is_kept(slot, same, at(9)) is True
    other = ScheduledItem(PlanItem(1, 0, (), 2, False), at(11), at(12))
    assert _is_kept(slot, other, at(9)) is False
    assert _is_kept(None, same, at(9)) is False
    assert _is_kept(slot, None, at(9)) is False


def test_mai_dropped_per_capacita():
    todos = [
        make_todo("A", todo_id=1, planned_for=TODAY, stima_pomo=2),
        make_todo("B", todo_id=2, planned_for=TODAY, stima_pomo=2),
        make_todo("C", todo_id=3, stima_pomo=4),
        make_todo("D", todo_id=4, stima_pomo=4),
    ]
    p = replan(todos, TODAY, 0.5, avail(), now=at(9))
    assert DROPPED not in kinds(p).values()
    assert kinds(p)[1] in (KEPT, MOVED) and kinds(p)[2] in (KEPT, MOVED)


def test_remaining_capacity_vs_remaining_time():
    todos = [make_todo("A", todo_id=1, planned_for=TODAY, stima_pomo=2)]
    busy = [TimeWindow(at(10), at(11))]
    p = replan(todos, TODAY, 6.0, avail(), busy, now=at(9))
    # Capacita': 12 pomo - 2 pianificati = 10; tempo: 9h - 1h busy = 8h.
    assert p.residual_pomo == 10
    assert p.remaining_min == 8 * 60
    assert p.residual_pomo != p.remaining_min  # unita' diverse, mai confusi


def test_remaining_time_dopo_now():
    todos = [make_todo("A", todo_id=1, planned_for=TODAY, stima_pomo=2)]
    p = replan(todos, TODAY, 6.0, avail(), now=at(15))
    assert p.remaining_min == 3 * 60


def test_completati_restano_fuori():
    todos = [
        make_todo("A", todo_id=1, planned_for=TODAY, stima_pomo=2),
        make_todo("B", todo_id=2, planned_for=TODAY, stima_pomo=2),
    ]
    todos[1].done = True
    todos[1].completed_at = TODAY + " 10:00"
    p = replan(todos, TODAY, 6.0, avail(), now=at(9))
    assert 2 not in kinds(p)


def test_current_senza_slot_kept_senza_orario():
    """current=None + nuovi senza slot (finestra esaurita): KEPT, mai MOVED."""
    todos = [make_todo("A", todo_id=1, planned_for=TODAY, stima_pomo=2)]
    p = replan(todos, TODAY, 6.0, avail(), now=at(20))
    assert kinds(p) == {1: KEPT}
    assert p.moves[0].new_start is None
    assert p.remaining_min == 0


def test_move_senza_slot_portano_alternativa_reale():
    """I move senza new_start (non DROPPED) espongono alt da diagnose."""
    from carpediem.planner.outcomes import OUT_ELIGIBLE, OUT_OUTSIDE, classify

    todos = [
        make_todo("A", todo_id=1, planned_for=TODAY, stima_pomo=2),
        make_todo("B", todo_id=2, planned_for=TODAY, stima_pomo=2),
        make_todo("C", todo_id=3, stima_pomo=8),  # 240m > finestra 180m
    ]
    window = [TimeWindow(at(9), at(12))]
    p = replan(todos, TODAY, 6.0, window, now=at(9))
    by_id = {m.todo_id: m for m in p.moves}
    # A e B confermati con slot: nessun alt (outcome = schedulato).
    assert by_id[1].new_start is not None and by_id[1].alt is None
    assert by_id[2].new_start is not None and by_id[2].alt is None
    # C aggiunto ma strutturalmente impossibile: alt reale fuori disponibilità.
    assert by_id[3].kind == ADDED and by_id[3].new_start is None
    assert by_id[3].alt is not None
    assert classify(by_id[3].alt.blocked_by) == OUT_OUTSIDE
    assert by_id[3].alt.detail["max_gap_min"] == 180
    assert classify("tasks") == OUT_ELIGIBLE  # gara persa = non inserito


def test_added_che_perde_la_gara_con_i_confermati():
    """Caso B §5: da solo entrerebbe, ma i confermati occupano -> ELIGIBLE."""
    from carpediem.planner.outcomes import OUT_ELIGIBLE, classify

    todos = [
        make_todo("A", todo_id=1, planned_for=TODAY, stima_pomo=2),
        make_todo("B", todo_id=2, planned_for=TODAY, stima_pomo=2),
        make_todo("C", todo_id=3, stima_pomo=6),  # 180m = finestra intera
    ]
    window = [TimeWindow(at(9), at(12))]
    p = replan(todos, TODAY, 6.0, window, now=at(9))
    by_id = {m.todo_id: m for m in p.moves}
    assert by_id[3].kind == ADDED and by_id[3].new_start is None
    assert by_id[3].alt is not None
    assert by_id[3].alt.blocked_by == "tasks"
    assert classify(by_id[3].alt.blocked_by) == OUT_ELIGIBLE


def test_kept_senza_orario_con_alt_fuori_disponibilita():
    """KEPT (None,None) a finestra esaurita: alt window, mai MOVED."""
    from carpediem.planner.outcomes import OUT_OUTSIDE, classify

    todos = [make_todo("A", todo_id=1, planned_for=TODAY, stima_pomo=2)]
    p = replan(todos, TODAY, 6.0, avail(), now=at(20))
    (m,) = p.moves
    assert m.kind == KEPT and m.new_start is None
    assert m.alt is not None and classify(m.alt.blocked_by) == OUT_OUTSIDE
