"""F2 scheduler gap-aware atomico: best-fit, slack-order, fuse, niente split."""

from datetime import date, datetime

from src.planner import DayPlan, PlanItem, TimeWindow, diagnose, schedule
from src.planner.models import PlanningRequest, PlanningResult

DAY = date(2026, 10, 8)
TODAY_S = "2026-10-08"


def at(h, m=0):
    return datetime(2026, 10, 8, h, m)


def win(sh, eh, sm=0, em=0):
    return TimeWindow(at(sh, sm), at(eh, em))


def item(tid, pomo=1, score=10):
    return PlanItem(tid, score, (), pomo, False)


def make_plan(*items):
    return DayPlan(
        day=DAY,
        planned=tuple(items),
        capacity_pomo=12.0,
        planned_pomo=sum(i.estimate_pomo for i in items),
    )


def slots(result):
    return [(s.item.todo_id, s.start, s.end) for s in result.scheduled]


def test_best_fit_piccolo_nel_buco_piccolo():
    """Small (30m, merito alto) non spreca il gap da 60m: va nel 30m."""
    plan = make_plan(item(1, pomo=1, score=50), item(2, pomo=2, score=10))
    r = schedule(plan, [win(9, 10), win(10, 11, 30, 0)])
    # Gap: 09:00-10:00 (60m) e 10:30-11:00 (30m).
    assert slots(r) == [(1, at(10, 30), at(11)), (2, at(9), at(10))]
    assert r.unscheduled == ()


def test_best_fit_tie_uguale_vince_inizio():
    plan = make_plan(item(1), item(2))
    r = schedule(plan, [win(9, 9, 0, 30), win(11, 11, 0, 30)])
    assert slots(r) == [(1, at(9), at(9, 30)), (2, at(11), at(11, 30))]


def test_slack_order_scadenza_stretta_prima():
    """A pari finestra, la deadline stretta vince sul merito (con now)."""
    plan = make_plan(item(1, pomo=1, score=50), item(2, pomo=1, score=10))
    deadlines = {1: (TODAY_S, "12:00"), 2: (TODAY_S, "10:00")}
    r = schedule(plan, [win(9, 9, 0, 30)], (), deadlines, now=at(9))
    # Un solo slot da 30m: slack 2 = 30, slack 1 = 150 -> 2 collocato.
    assert [s.item.todo_id for s in r.scheduled] == [2]
    assert [i.todo_id for i in r.unscheduled] == [1]


def test_slack_order_senza_now_legacy():
    """Senza now: ordine legacy (scadenza odierna prima, poi merito)."""
    plan = make_plan(item(1, pomo=1, score=50), item(2, pomo=1, score=10))
    deadlines = {1: (TODAY_S, "12:00"), 2: (TODAY_S, "10:00")}
    r = schedule(plan, [win(9, 9, 0, 30)], (), deadlines)
    assert [s.item.todo_id for s in r.scheduled] == [1]
    assert [i.todo_id for i in r.unscheduled] == [2]


def test_atomico_90_con_3_buchi_da_30():
    """90m con tre buchi da 30m: unscheduled, niente split, motivo reale."""
    plan = make_plan(item(1, pomo=3))
    avail = [win(9, 12)]
    busy = [win(9, 10, 30, 0), win(10, 11, 30, 30)]
    r = schedule(plan, avail, busy)
    assert r.scheduled == ()
    assert [i.todo_id for i in r.unscheduled] == [1]
    req = PlanningRequest(day=DAY, tasks=(), capacity_pomo=12.0)
    alts, _diags = diagnose(PlanningResult(request=req, plan=plan, scheduled=r), ())
    assert len(alts) == 1
    alt = alts[0]
    # Togliendo i busy entrerebbe (180m liberi): il blocco osservato e' busy,
    # con le dimensioni reali dei buchi per spiegare la frammentazione.
    assert alt.blocked_by == "busy"
    assert alt.detail["needed_min"] == 90
    assert alt.detail["max_gap_min"] == 30
    assert alt.detail["gap_count"] == 3


def test_atomico_finestra_corta_senza_busy():
    """90m con finestra da 60m e niente busy: blocco window strutturato."""
    plan = make_plan(item(1, pomo=3))
    r = schedule(plan, [win(9, 10)])
    assert r.scheduled == ()
    req = PlanningRequest(day=DAY, tasks=(), capacity_pomo=12.0)
    alts, _diags = diagnose(PlanningResult(request=req, plan=plan, scheduled=r), ())
    assert len(alts) == 1
    assert alts[0].blocked_by == "window"
    assert alts[0].detail == {
        "needed_min": 90,
        "max_gap_min": 60,
        "gap_count": 1,
    }


def test_availability_sovrapposte_fuse():
    """09-12 + 11-14 fuse in 09-14: task da 3h collocato, niente double."""
    plan = make_plan(item(1, pomo=6))
    r = schedule(plan, [win(9, 12), win(11, 14)])
    assert r.availability == (win(9, 14),)
    assert slots(r) == [(1, at(9), at(12))]


def test_availability_contigue_fuse():
    plan = make_plan(item(1, pomo=2))
    r = schedule(plan, [win(9, 10), win(10, 11)])
    assert r.availability == (win(9, 11),)
    assert slots(r) == [(1, at(9), at(10))]


def test_best_fit_deterministico():
    plan = make_plan(item(1, pomo=1, score=50), item(2, pomo=2, score=10))
    avail = [win(9, 10), win(10, 11, 30, 0)]
    first = slots(schedule(plan, avail))
    second = slots(schedule(plan, avail))
    assert first == second == [(1, at(10, 30), at(11)), (2, at(9), at(10))]


def test_singolo_gap_identico_al_legacy():
    """Un solo gap: best-fit = first-fit (differenziale §11 invariato)."""
    plan = make_plan(item(1), item(2, pomo=2))
    r = schedule(plan, [win(9, 12)])
    assert slots(r) == [(1, at(9), at(9, 30)), (2, at(9, 30), at(10, 30))]


def test_scadenza_taglia_il_waste():
    """Il waste si misura sulla fine effettiva (min(slot, scadenza))."""
    plan = make_plan(item(1, pomo=1, score=10))
    deadlines = {1: (TODAY_S, "09:30")}
    # Gap 09:00-12:00 ma scadenza 09:30: waste 0 effettivo, collocato.
    r = schedule(plan, [win(9, 12)], (), deadlines, now=at(8))
    assert slots(r) == [(1, at(9), at(9, 30))]
