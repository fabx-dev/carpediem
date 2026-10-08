"""F1 now-binding: clip a now in Buongiorno/piano, niente slot nel passato."""

from datetime import datetime

from carpediem.lang import T as _T
from carpediem.screens.plan import (
    PlanProposalScreen,
    build_planning_request,
    scheduled_for_today,
)
from tests.conftest import make_todo

TODAY = "2026-10-08"
NOW = datetime(2026, 10, 8, 15, 0)
WINDOW = {"date": TODAY, "start": "09:00", "end": "18:00", "events": []}


def _todos():
    return [
        make_todo("A", todo_id=1, stima_pomo=2),
        make_todo("B", todo_id=2, stima_pomo=1),
    ]


def _confirmed():
    todos = _todos()
    for t in todos:
        t.planned_for = TODAY
    return todos


def test_scheduled_for_today_clippa_a_now():
    sched, _ev, _al, planned, _alts = scheduled_for_today(
        _confirmed(), TODAY, 6.0, WINDOW, now=NOW
    )
    assert sched is not None and sched.availability
    assert sched.availability[0].start == NOW
    for s in sched.scheduled:
        assert s.start >= NOW
    assert planned


def test_scheduled_for_today_finestra_trascorsa_degrada():
    sched, _ev, _al, planned, _alts = scheduled_for_today(
        _confirmed(), TODAY, 6.0, WINDOW, now=datetime(2026, 10, 8, 19, 0)
    )
    assert sched is not None and not sched.availability
    assert sched.scheduled == () and sched.plan.planned
    assert planned  # solo task, zero timeline


def test_scheduled_for_today_senza_now_legacy():
    sched, _ev, _al, _pl, _alts = scheduled_for_today(_confirmed(), TODAY, 6.0, WINDOW)
    assert sched.availability[0].start == datetime(2026, 10, 8, 9, 0)


def test_build_request_inoltra_now_e_plan_clippa():
    import carpediem.planner as p

    req = build_planning_request(_todos(), TODAY, 6.0, WINDOW, now=NOW)
    assert req.now == NOW
    res = p.plan(req)
    assert res.scheduled.availability[0].start == NOW
    assert res.scheduled.availability[0].end == datetime(2026, 10, 8, 18, 0)


def test_buongiorno_mostra_fascia_esclusa_e_slot_futuri():
    screen = PlanProposalScreen(
        _todos(), lambda *a: None, today=TODAY, hours=6.0, now=NOW
    )
    screen.start_text = "09:00"
    screen.end_text = "18:00"
    screen._refresh_sched()
    assert screen.past_note is not None
    assert screen.sched is not None
    for s in screen.sched.scheduled:
        assert s.start >= NOW
    lines = screen._slot_lines()
    assert _T("planp_past", s="09:00", e="15:00", n="15:00") in lines


def test_buongiorno_finestra_trascorsa_solo_task():
    screen = PlanProposalScreen(
        _todos(),
        lambda *a: None,
        today=TODAY,
        hours=6.0,
        now=datetime(2026, 10, 8, 19, 0),
    )
    screen.start_text = "09:00"
    screen.end_text = "18:00"
    screen._refresh_sched()
    assert screen.sched is None
    lines = screen._slot_lines()
    assert _T("planp_slots_none") in lines
    assert _T("planp_past", s="09:00", e="18:00", n="19:00") in lines


def test_buongiorno_prefill_con_nota_passato():
    screen = PlanProposalScreen(
        _todos(),
        lambda *a: None,
        today=TODAY,
        hours=6.0,
        prev_start="09:00",
        prev_end="18:00",
        prev_date="2026-10-07",
        now=NOW,
    )
    assert screen.prefill_date == "2026-10-07"
    assert screen.past_note is not None
    assert _T("planp_prefill_past", n="15:00")
