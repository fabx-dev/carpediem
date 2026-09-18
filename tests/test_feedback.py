"""Test feedback di esecuzione (Fase 5: derivazione pura, senza Textual)."""

from datetime import date, datetime

from src.domain import calibration_factor, credit_pomodoro, record_actual
from src.planner import DayPlan, PlanItem, Planner, TimeWindow, feedback, schedule
from tests.conftest import make_todo

TODAY = "2026-09-10"


def at(h, m=0):
    return datetime(2026, 9, 10, h, m)


def _run(todos, hours=6.0, avail=None, **kw):
    plan = Planner(todos, today=TODAY, hours=hours, **kw).propose()
    sched = schedule(plan, avail or [TimeWindow(at(9), at(18))])
    return plan, sched, feedback(sched, todos)


def test_scheduled_collegato_con_stime_e_slot():
    todos = [make_todo("A", todo_id=1, stima_pomo=2), make_todo("B", todo_id=2)]
    plan, sched, fb = _run(todos)
    assert [f.todo_id for f in fb] == [1, 2]
    assert (fb[0].estimate_pomo, fb[0].estimate_minutes) == (2, 60)
    assert (fb[1].estimate_pomo, fb[1].estimate_minutes) == (1, 30)
    assert (fb[0].scheduled_start, fb[0].scheduled_end) == (
        sched.scheduled[0].start,
        sched.scheduled[0].end,
    )
    assert (fb[0].sessions, fb[0].actual_pomo, fb[0].actual_minutes) == (0, 0, 0)
    assert fb[0].completed is False


def test_unscheduled_presente_senza_slot():
    # Capacity ok (6h) ma availability corta (1h): planned ma non collocabile.
    todos = [make_todo("A", todo_id=1, stima_pomo=4)]
    plan, sched, fb = _run(todos, avail=[TimeWindow(at(9), at(10))])
    assert [i.todo_id for i in plan.planned] == [1]
    assert [i.todo_id for i in sched.unscheduled] == [1]
    assert len(fb) == 1
    assert fb[0].scheduled_start is None and fb[0].scheduled_end is None
    assert fb[0].estimate_pomo == 4


def test_sessioni_multiple_e_interruzione():
    todos = [make_todo("A", todo_id=1), make_todo("B", todo_id=2)]
    credit_pomodoro(todos[0], "2026-09-10 09:30")
    credit_pomodoro(todos[0], "2026-09-10 10:30")
    # B: sessione interrotta = nessuno stop/credito, solo tempo perso.
    _plan, _sched, fb = _run(todos)
    assert fb[0].sessions == 2
    assert fb[1].sessions == 0


def test_actual_manuale_distinto_dalle_sessioni():
    todos = [make_todo("A", todo_id=1)]
    credit_pomodoro(todos[0], "2026-09-10 09:30")
    record_actual(todos[0], 5, 120)
    (_fb,) = _run(todos)[2]
    assert (_fb.sessions, _fb.actual_pomo, _fb.actual_minutes) == (1, 5, 120)


def test_completed_indipendente_dall_actual():
    todos = [make_todo("A", todo_id=1), make_todo("B", todo_id=2)]
    credit_pomodoro(todos[0], "2026-09-10 09:30")  # lavorato ma non completato
    todos[1].done = True  # completato senza pomodoro
    _plan, _sched, fb = _run(todos)
    by_id = {f.todo_id: f for f in fb}
    assert by_id[1].completed is False and by_id[1].sessions == 1
    # B completato: esce dagli eleggibili, quindi niente feedback (non planned).
    assert 2 not in by_id


def test_completato_con_pomodoro_tutto_distinto():
    t = make_todo("A", todo_id=1, stima_pomo=2)
    credit_pomodoro(t, "2026-09-10 09:30")
    record_actual(t, 3, 75)
    plan = DayPlan(
        day=date(2026, 9, 10),
        planned=(PlanItem(1, 10, (), 2, False),),
    )
    sched = schedule(plan, [TimeWindow(at(9), at(18))])
    (fb,) = feedback(sched, [t])
    assert (fb.estimate_pomo, fb.estimate_minutes) == (2, 60)
    assert (fb.scheduled_start, fb.scheduled_end) == (at(9), at(10))
    assert (fb.sessions, fb.actual_pomo, fb.actual_minutes) == (1, 3, 75)
    assert fb.completed is False


def test_feedback_non_tocca_nulla():
    todos = [make_todo("A", todo_id=1, stima_pomo=2)]
    plan, sched, fb = _run(todos)
    before = [(t.pomodoros, t.actual_pomo, t.actual_minutes, t.state) for t in todos]
    feedback(sched, todos)
    after = [(t.pomodoros, t.actual_pomo, t.actual_minutes, t.state) for t in todos]
    assert before == after
    assert calibration_factor(todos) is None  # invariato: nessun campione
    assert plan.to_legacy() == sched.plan.to_legacy()


def test_conversione_unica_fonte():
    from src.planner.capacity import POMO_HOURS

    assert POMO_HOURS == 0.5
    todos = [make_todo("A", todo_id=1, stima_pomo=4)]
    (_fb,) = _run(todos)[2]
    assert _fb.estimate_minutes == int(POMO_HOURS * 60 * 4) == 120


def test_determinismo_e_ordine_planned():
    todos = [
        make_todo("A", todo_id=1),
        make_todo("B", todo_id=2, due="2026-09-09"),
        make_todo("C", todo_id=3, plan_skip=TODAY),
    ]
    _plan, sched, fb = _run(todos)
    assert [f.todo_id for f in fb] == [i.todo_id for i in sched.plan.planned]
    assert _run(todos)[2] == fb
