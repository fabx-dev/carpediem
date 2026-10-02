"""Phase 6 Step P6-2 — D2/D3/D4/D5: diagnose() golden (piano revisionato §4/§7).

Ogni riga: primo blocco atteso + coerenza probe≡scheduler reale.
Risultati assemblati a mano (nessun consumer ancora — P6-3 li popola).
"""

from datetime import date, datetime

from src.planner import Planner
from src.planner.diagnostics import diagnose
from src.planner.models import (
    DayPlan,
    PlanItem,
    PlanningRequest,
    PlanningResult,
    TimeWindow,
)
from tests.conftest import make_todo

DAY = date(2026, 9, 10)
TODAY_S = "2026-09-10"


def _win(h1, m1, h2, m2):
    return TimeWindow(datetime(2026, 9, 10, h1, m1), datetime(2026, 9, 10, h2, m2))


def _result(todos, hours=6.0, avail=(), busy=(), factor=None):
    req = PlanningRequest(
        day=DAY, tasks=todos, capacity_pomo=hours / 0.5, factor=factor
    )
    plan = Planner(todos, today=TODAY_S, hours=hours, factor=factor).propose()
    if avail:
        from src.planner.scheduler import deadlines_for

        sched = Planner.schedule(plan, avail, busy, deadlines_for(todos))
    else:
        sched = None
    return PlanningResult(request=req, plan=plan, scheduled=sched)


def test_cut_capacity_e_skip_user():
    todos = [make_todo(f"T{i}", todo_id=i) for i in range(1, 8)]
    alts, diags = diagnose(_result(todos, hours=1.0, avail=[_win(9, 0, 18, 0)]))
    assert {a.todo_id for a in alts} == {3, 4, 5, 6, 7}
    assert all(
        a.decision == "not_scheduled" and a.blocked_by == "capacity" for a in alts
    )
    assert all(set(a.detail) <= {"estimate_pomo"} for a in alts)
    sk = [make_todo("S", todo_id=1, plan_skip=TODAY_S)]
    alts2, _ = diagnose(_result(sk))
    assert [(a.decision, a.blocked_by, a.detail) for a in alts2] == [
        ("deferred", "user_skip", {})
    ]
    assert diags == ()


def test_duration_oltre_giornata():
    plan = DayPlan(day=DAY, planned=(PlanItem(1, 10, (), 50, True),))
    req = PlanningRequest(day=DAY, tasks=(), capacity_pomo=16.0)
    sched = Planner.schedule(plan, [_win(9, 0, 18, 0)], ())
    assert [it.todo_id for it in sched.unscheduled] == [1]
    alts, diags = diagnose(PlanningResult(request=req, plan=plan, scheduled=sched))
    assert [(a.decision, a.blocked_by) for a in alts] == [("constrained", "duration")]
    assert alts[0].detail["needed_min"] == 50 * 30
    assert [d.kind for d in diags] == ["constrained_mandatory"]
    assert diags[0].detail == {"count": 1, "todo_ids": (1,)}


def test_deadline_e_busy_e_window():
    # Deadline: 2 pomo non entrano entro le 09:30.
    todos = [make_todo("A", todo_id=1, due=f"{TODAY_S} 09:30", stima_pomo=2)]
    alts, _ = diagnose(_result(todos, avail=[_win(9, 0, 18, 0)]))
    assert [(a.decision, a.blocked_by) for a in alts] == [("constrained", "deadline")]
    assert alts[0].detail == {"needed_min": 60, "deadline": "09:30"}
    # Busy: giorno intero occupato.
    todos_b = [make_todo("B", todo_id=2)]
    alts_b, _ = diagnose(
        _result(todos_b, avail=[_win(9, 0, 18, 0)], busy=[_win(9, 0, 18, 0)])
    )
    assert [(a.blocked_by) for a in alts_b] == ["busy"]
    # Window: gara persa ma entrerebbe da solo.
    c = PlanItem(1, 30, (), 2, False)
    d = PlanItem(2, 10, (), 2, False)
    plan = DayPlan(day=DAY, planned=(c, d))
    req = PlanningRequest(day=DAY, tasks=(), capacity_pomo=16.0)
    sched = Planner.schedule(plan, [_win(9, 0, 10, 0)], ())
    alts_c, _ = diagnose(PlanningResult(request=req, plan=plan, scheduled=sched))
    assert [(a.todo_id, a.decision, a.blocked_by) for a in alts_c] == [
        (2, "scheduled", "window")
    ]


def test_multi_blocco_ordine_documentato():
    """Deadline + busy insieme: vince deadline (primo in ordine), mai causa unica."""
    todos = [make_todo("A", todo_id=1, due=f"{TODAY_S} 10:00")]
    alts, _ = diagnose(
        _result(todos, avail=[_win(9, 0, 18, 0)], busy=[_win(9, 0, 12, 0)])
    )
    assert [a.blocked_by for a in alts] == ["deadline"]


def test_overflow_e_availability_vuota():
    todos = [
        make_todo("S", todo_id=1, due="2026-09-01", stima_pomo=4),
        make_todo("P", todo_id=2, planned_for=TODAY_S, stima_pomo=4),
    ]
    _, diags = diagnose(_result(todos, hours=0.5))
    by_kind = {d.kind: d.detail for d in diags}
    assert by_kind["overflow"] == {
        "planned_pomo": 8,
        "capacity_pomo": 1.0,
        "over_pomo": 7.0,
    }
    # Scheduling tentato con availability vuota: diagnostica + window a testa.
    req = PlanningRequest(day=DAY, tasks=todos, capacity_pomo=12.0)
    plan = Planner(todos, today=TODAY_S, hours=6.0).propose()
    sched_empty = Planner.schedule(plan, [], ())
    alts, diags2 = diagnose(
        PlanningResult(request=req, plan=plan, scheduled=sched_empty)
    )
    by_kind = {d.kind: d.detail for d in diags2}
    assert by_kind["empty_availability"] == {"planned_count": 2}
    # S e' mandatory senza slot: anche constrained, entrambe vere insieme.
    assert by_kind["constrained_mandatory"] == {"count": 1, "todo_ids": (1,)}
    assert all(a.blocked_by == "window" for a in alts)
    # Senza tentativo (scheduled None): solo cut/skip, mai window spurie.
    alts3, diags3 = diagnose(PlanningResult(request=req, plan=plan, scheduled=None))
    assert all(a.blocked_by != "window" for a in alts3)
    assert [d.kind for d in diags3] == []


def test_sano_niente_diagnostics_e_determinismo():
    todos = [make_todo("A", todo_id=1), make_todo("B", todo_id=2)]
    res = _result(todos, avail=[_win(9, 0, 18, 0)])
    assert diagnose(res) == ((), ())
    # D3: stesso input, stesso output (incl. ordine).
    res2 = _result(list(reversed(todos)), avail=[_win(9, 0, 18, 0)])
    assert diagnose(res) == diagnose(res2) == ((), ())


def test_facade_popola_coerente_con_manuale():
    """P6-3: plan() riempie alternatives/diagnostics come diagnose() manuale;
    i campi vecchi restano identici (E1)."""
    from src.planner import plan

    todos = [
        make_todo("A", todo_id=1, due=f"{TODAY_S} 09:30", stima_pomo=2),
        make_todo("B", todo_id=2),
    ]
    req = PlanningRequest(
        day=DAY, tasks=todos, capacity_pomo=12.0, availability=[_win(9, 0, 18, 0)]
    )
    res = plan(req)
    assert res.alternatives, res.diagnostics
    manual = diagnose(
        PlanningResult(
            request=req,
            plan=res.plan,
            scheduled=res.scheduled,
            decisions=res.decisions,
        )
    )
    assert (res.alternatives, res.diagnostics) == manual
    assert [a.blocked_by for a in res.alternatives] == ["deadline"]


def test_coerenza_probe_scheduler_e_totalita():
    """D2: per ogni unscheduled, il re-schedule single-item con vincoli pieni
    fallisce come lo scheduler reale; diagnose() mai solleva."""
    from src.planner.scheduler import schedule

    todos = [make_todo("A", todo_id=1, due=f"{TODAY_S} 09:30", stima_pomo=2)]
    res = _result(todos, avail=[_win(9, 0, 18, 0)])
    (alt,) = diagnose(res)[0]
    solo = DayPlan(day=DAY, planned=tuple(res.plan.planned[:1]))
    from src.planner.scheduler import deadlines_for

    assert schedule(solo, [_win(9, 0, 18, 0)], (), deadlines_for(todos)).scheduled == ()
    assert diagnose(object()) == ((), ())
    assert diagnose(None) == ((), ())


def test_scaduto_senza_orario_mai_deadline():
    """Regressione card reale: task scaduto con due solo-data non deve mai
    produrre blocked_by=deadline (né 'scadenza alle .' vuota) — la deadline
    vale solo per due-date == day + orario, come lo scheduler."""
    todos = [make_todo("A", todo_id=1, due="2026-09-01", stima_pomo=4)]
    res = _result(todos, avail=[_win(9, 0, 10, 0)])
    (alt,) = diagnose(res)[0]
    assert alt.blocked_by != "deadline"
    assert "deadline" not in (alt.detail or {})
    from src.screens.views import _blocked_line

    line = _blocked_line(alt)
    assert line is None or "alle ." not in line


def test_deadline_sempre_con_orario():
    todos = [make_todo("A", todo_id=1, due=f"{TODAY_S} 09:30", stima_pomo=2)]
    res = _result(todos, avail=[_win(9, 0, 18, 0)])
    (alt,) = diagnose(res)[0]
    assert alt.blocked_by == "deadline"
    assert (alt.detail or {}).get("deadline") == "09:30"


def test_blocked_line_senza_orario_non_rende():
    """Difesa in profondità: deadline senza HH:MM = nessuna riga, mai testo rotto."""
    from src.planner.models import PlanAlternative
    from src.screens.views import _blocked_line

    assert _blocked_line(None) is None
    assert _blocked_line(PlanAlternative(1, "scheduled", "deadline", {})) is None
    assert (
        _blocked_line(PlanAlternative(1, "scheduled", "deadline", {"deadline": ""}))
        is None
    )
    assert "09:30" in _blocked_line(
        PlanAlternative(1, "scheduled", "deadline", {"deadline": "09:30"})
    )


def test_busy_nomina_gli_eventi():
    """Blocco busy con eventi noti: i titoli finiscono nel detail (di che
    impegni si parla); senza eventi, causa generica come prima."""
    from src.planner.diagnostics import diagnose
    from src.planner.models import FixedEvent, PlanningRequest, PlanningResult

    big = [make_todo("B", todo_id=2, stima_pomo=6)]  # 3h: in 16-18 non entra
    plan2 = Planner(big, today=TODAY_S, hours=6.0).propose()
    sched2 = Planner.schedule(plan2, [_win(9, 0, 18, 0)], [_win(9, 0, 16, 0)])
    assert [it.todo_id for it in sched2.unscheduled] == [2]
    ev = FixedEvent("Pranzo", datetime(2026, 9, 10, 9, 0), datetime(2026, 9, 10, 16, 0))
    req2 = PlanningRequest(day=DAY, tasks=big, capacity_pomo=12.0)
    alts, _ = diagnose(PlanningResult(request=req2, plan=plan2, scheduled=sched2), [ev])
    assert [(a.blocked_by, (a.detail or {}).get("busy_titles")) for a in alts] == [
        ("busy", ("Pranzo",))
    ]
    alts_gen, _ = diagnose(PlanningResult(request=req2, plan=plan2, scheduled=sched2))
    assert (alts_gen[0].detail or {}).get("busy_titles") is None
    assert alts_gen[0].blocked_by == "busy"
