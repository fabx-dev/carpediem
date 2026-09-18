"""Test scheduler temporale (Fase 4: puro, deterministico, senza Textual)."""

from datetime import date, datetime, timedelta

from src.plan import plan_day
from src.planner import (
    DayPlan,
    PlanItem,
    Planner,
    ScheduledDayPlan,
    TimeWindow,
    schedule,
)
from tests.conftest import make_todo

DAY = date(2026, 9, 10)
TODAY = "2026-09-10"


def at(h, m=0):
    return datetime(2026, 9, 10, h, m)


def win(sh, eh, sm=0, em=0):
    return TimeWindow(at(sh, sm), at(eh, em))


def item(tid, pomo=1, mandatory=False, score=10):
    return PlanItem(tid, score, (), pomo, mandatory)


def make_plan(*items, **kw):
    kw.setdefault("capacity_pomo", 12.0)
    kw.setdefault("planned_pomo", sum(i.estimate_pomo for i in items))
    return DayPlan(day=DAY, planned=tuple(items), **kw)


def slots(result):
    return [(s.item.todo_id, s.start, s.end) for s in result.scheduled]


def test_singolo_task_a_inizio_finestra():
    r = schedule(make_plan(item(1)), [win(9, 10)])
    assert slots(r) == [(1, at(9), at(9, 30))]
    assert r.unscheduled == ()


def test_piu_task_sequenziali():
    r = schedule(make_plan(item(1), item(2, pomo=2)), [win(9, 12)])
    assert slots(r) == [(1, at(9), at(9, 30)), (2, at(9, 30), at(10, 30))]


def test_busy_sposta_dopo():
    # A da 1h entra prima del busy, B da 30min no -> dopo il busy.
    r = schedule(
        make_plan(item(1, pomo=2), item(2)),
        [win(9, 12)],
        [win(10, 10, 0, 30)],
    )
    assert slots(r) == [(1, at(9), at(10)), (2, at(10, 30), at(11))]


def test_busy_divide_la_giornata():
    r = schedule(
        make_plan(item(1, pomo=4), item(2, pomo=2)),
        [win(9, 12), win(14, 18)],
        [win(10, 10, 0, 30)],
    )
    assert slots(r) == [(1, at(14), at(16)), (2, at(9), at(10))]


def test_task_troppo_lungo_unscheduled():
    r = schedule(make_plan(item(1, pomo=4)), [win(9, 10)])
    assert r.scheduled == () and [i.todo_id for i in r.unscheduled] == [1]


def test_cut_e_skipped_non_si_schedulano():
    plan = DayPlan(
        day=DAY,
        planned=(item(1),),
        cut=(item(2),),
        skipped=(item(3),),
    )
    r = schedule(plan, [win(9, 18)])
    assert [s.item.todo_id for s in r.scheduled] == [1]
    assert r.unscheduled == ()


def test_overflow_temporale():
    plan = make_plan(item(1, pomo=4), item(2, pomo=4), item(3, pomo=4))
    r = schedule(plan, [win(9, 12)])  # 3h libere, servono 6h
    assert [s.item.todo_id for s in r.scheduled] == [1]
    assert [i.todo_id for i in r.unscheduled] == [2, 3]


def test_mandatory_senza_slot_resta_unscheduled():
    plan = make_plan(item(1, pomo=6, mandatory=True), item(2))
    r = schedule(plan, [win(9, 10)])
    assert [s.item.todo_id for s in r.scheduled] == [2]
    assert [i.todo_id for i in r.unscheduled] == [1]
    assert r.unscheduled[0].mandatory is True
    assert all("plan_unscheduled" != k for i in r.unscheduled for k, _p in i.reasons)


def test_confini_esatti_e_busy_adiacenti():
    # Il primo finisce esattamente all'inizio del busy, il secondo inizia
    # esattamente alla fine; i busy adiacenti si fondono in uno solo.
    r = schedule(
        make_plan(item(1, pomo=2), item(2)),
        [win(9, 12)],
        [win(10, 10, 0, 30), win(10, 11, 30, 0)],  # adiacenti -> un solo busy
    )
    assert r.busy == (win(10, 11),)
    assert slots(r) == [(1, at(9), at(10)), (2, at(11), at(11, 30))]


def test_busy_sovrapposti_e_fuori_giorno():
    r = schedule(
        make_plan(item(1)),
        [win(9, 12)],
        [win(9, 9, 0, 30), win(9, 10, 15, 0), TimeWindow(at(8), at(9, 15))],
    )
    assert r.busy == (win(8, 10),)
    assert slots(r) == [(1, at(10), at(10, 30))]


def test_disponibilita_vuota_e_finestre_invalide():
    plan = make_plan(item(1))
    assert schedule(plan, []).unscheduled == (plan.planned[0],)
    bad = [TimeWindow(at(10), at(9)), TimeWindow(at(9), at(9)), "xx", None]
    r = schedule(plan, bad)
    assert r.scheduled == () and r.availability == ()


def test_durata_rispetta_stima_calibrata():
    todos = [make_todo("A", todo_id=1, stima_pomo=1)]
    plan = Planner(todos, today=TODAY, factor=2.0).propose()
    assert plan.planned[0].estimate_pomo == 2
    r = schedule(plan, [win(9, 12)])
    (s,) = r.scheduled
    assert s.end - s.start == timedelta(hours=1)
    assert s.item.score == plan.planned[0].score
    assert s.item.reasons == plan.planned[0].reasons


def test_invarianti_su_scenario_misto():
    plan = make_plan(
        item(1, pomo=2, mandatory=True),
        item(2, pomo=3),
        item(3, pomo=1),
        item(4, pomo=6),
    )
    avail = [win(9, 12), win(13, 17)]
    busy = [win(10, 10, 0, 30), win(14, 14, 0, 30)]
    r = schedule(plan, avail, busy)
    ordered = sorted(r.scheduled, key=lambda s: s.start)
    assert [s.item.todo_id for s in ordered] == [1, 2, 3]
    assert [i.todo_id for i in r.unscheduled] == [4]
    for a, b in zip(ordered, ordered[1:]):
        assert a.end <= b.start  # nessun overlap
    for s in ordered:
        assert any(w.start <= s.start and s.end <= w.end for w in avail)
        assert all(b.end <= s.start or s.end <= b.start for b in r.busy)
        assert s.end - s.start == timedelta(minutes=30 * s.item.estimate_pomo)
    assert {s.item.todo_id for s in ordered} <= {i.todo_id for i in plan.planned}


def test_determinismo_e_wrapper_planner():
    plan = make_plan(item(1, pomo=2), item(2))
    args = ([win(9, 12), win(14, 15)], [win(10, 10, 0, 15)])
    assert schedule(plan, *args) == schedule(plan, *args)
    assert Planner.schedule(plan, *args) == schedule(plan, *args)
    assert isinstance(schedule(plan, *args), ScheduledDayPlan)


def test_schedule_non_muta_il_dayplan():
    todos = [make_todo("A", todo_id=1), make_todo("B", todo_id=2, due=TODAY)]
    plan = Planner(todos, today=TODAY).propose()
    before = plan.to_legacy()
    schedule(plan, [win(9, 18)])
    assert plan.to_legacy() == before == plan_day(todos, TODAY)


def test_durata_zero_slot_puntuale():
    r = schedule(make_plan(item(1, pomo=0)), [win(9, 10)])
    assert slots(r) == [(1, at(9), at(9))]
