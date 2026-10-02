"""Phase 2 Step P2-3 — adapter build_planning_request().

L'adapter e' l'unico punto app->core: factor auto, ore->pomo, finestra->
availability/busy. Nessun consumer migrato ancora (P2-6): qui solo il
contratto dell'adapter + equivalenza via facade."""

from datetime import datetime

from src.domain import calibration_factor
from src.planner import Planner, plan
from src.screens.plan import build_planning_request
from tests.conftest import make_todo

TODAY_S = "2026-09-10"
DAY = (2026, 9, 10)


def _todos():
    return [
        make_todo("A-ritardo", todo_id=1, due="2026-09-09", stima_pomo=2),
        make_todo("B-oggi", todo_id=2, due=TODAY_S),
        make_todo("C-skip", todo_id=3, plan_skip=TODAY_S),
    ]


def _window():
    return {
        "date": TODAY_S,
        "start": "09:00",
        "end": "18:00",
        "events": [{"start": "12:00", "end": "13:00", "title": "Pausa"}],
    }


def test_adapter_factor_auto_come_legacy():
    todos = _todos()
    req = build_planning_request(todos, TODAY_S, 6.0, None)
    assert req.factor == calibration_factor(todos)
    assert req.factor == Planner(todos, today=TODAY_S, hours=6.0).propose().factor
    assert req.capacity_pomo == 12.0
    assert str(req.day) == TODAY_S


def test_adapter_finestra_availability_busy():
    req = build_planning_request(_todos(), TODAY_S, 6.0, _window())
    assert len(req.availability) == 1
    assert req.availability[0].start == datetime(*DAY, 9, 0)
    assert req.availability[0].end == datetime(*DAY, 18, 0)
    assert len(req.busy) == 1  # la pausa pranzo
    assert req.busy[0].start == datetime(*DAY, 12, 0)


def test_adapter_senza_finestra_solo_task():
    req = build_planning_request(_todos(), TODAY_S, 6.0, None)
    assert req.availability == () and req.busy == ()
    req_bad = build_planning_request(_todos(), TODAY_S, 6.0, {"start": "xx"})
    assert req_bad.availability == ()


def test_adapter_via_facade_uguale_a_legacy():
    todos = _todos()
    req = build_planning_request(todos, TODAY_S, 6.0, _window())
    res = plan(req)
    legacy = Planner(todos, today=TODAY_S, hours=6.0).propose()
    assert res.plan == legacy
    assert res.scheduled == Planner.schedule(
        legacy, list(req.availability), list(req.busy)
    )


def test_adapter_ore_e_today_tolleranti():
    assert build_planning_request(_todos(), TODAY_S, "xx", None).capacity_pomo == 0.0
    req = build_planning_request(_todos(), "xx", 6.0, None)
    assert req.day == datetime.now().date()  # orologio del caller, documentato


def test_e2_scheduled_for_today_golden():
    """E2 (P2-6): scheduled_for_today via facade — slot espliciti pinnati,
    completati-oggi fuori dal dayplan ma nei confermati (briefing)."""
    from src.screens.plan import scheduled_for_today

    done = make_todo("C", todo_id=3, completed_at=f"{TODAY_S} 16:00")
    done.done = True
    done.planned_for = ""  # apply_state azzera al completamento: conta completed_at
    todos = [
        make_todo("A", todo_id=1, planned_for=TODAY_S, stima_pomo=2),
        make_todo("B", todo_id=2, planned_for=TODAY_S, stima_pomo=2),
        done,
    ]
    sched, events, _allday, planned, _alts = scheduled_for_today(
        todos, TODAY_S, 6.0, _window()
    )
    slots = {s.item.todo_id: s for s in sched.scheduled}
    assert [
        (s.start.strftime("%H:%M"), s.end.strftime("%H:%M")) for s in sched.scheduled
    ] == [
        ("09:00", "10:00"),
        ("10:00", "11:00"),
    ]
    assert set(slots) == {1, 2}
    assert [t.id for t in planned] == [1, 2]  # il completato resta fuori
    assert len(events) == 1 and events[0].title == "Pausa"

    sched2, _ev, _al, planned2, _alts2 = scheduled_for_today(
        todos, TODAY_S, 6.0, _window(), include_done=True
    )
    assert [t.id for t in planned2] == [1, 2, 3]
    in_plan = {s.item.todo_id for s in sched2.scheduled} | {
        it.todo_id for it in sched2.unscheduled
    }
    assert 3 not in in_plan  # non-attivi mai schedulati, slot None
    assert sched2 is not None and sched2.plan is not None
