"""Eventi fissi Fase 7: parsing, proiezione busy, scheduling (senza Textual)."""

from dataclasses import FrozenInstanceError
from datetime import datetime

import pytest

from src.planner import (
    DayPlan,
    FixedEvent,
    PlanItem,
    TimeWindow,
    events_to_busy,
    schedule,
)
from src.screens.plan import parse_event_lines

DAY = "2026-09-10"


def at(h, m=0):
    return datetime(2026, 9, 10, h, m)


def item(tid, pomo=1, mandatory=False):
    return PlanItem(tid, 10, (), pomo, mandatory)


def plan(*items):
    return DayPlan(day=at(0).date(), planned=tuple(items))


def test_parse_formato_base_e_multipli():
    events, bad = parse_event_lines("11:00-12:00 Riunione\n14:30-15:00 Call", DAY)
    assert bad == []
    assert events == [
        FixedEvent("Riunione", at(11), at(12)),
        FixedEvent("Call", at(14, 30), at(15)),
    ]


def test_parse_tollerante_e_invalide_segnalate():
    events, bad = parse_event_lines(
        "11:00–12:00 En-dash ok\n\n12:00-11:00 Invertito\nxx\n25:00-26:00 Ore\n"
        "09:00-09:30",
        DAY,
    )
    assert [e.title for e in events] == ["En-dash ok", ""]
    assert bad == ["12:00-11:00 Invertito", "xx", "25:00-26:00 Ore"]


def test_fixed_event_immutabile():
    with pytest.raises(FrozenInstanceError):
        FixedEvent("X", at(9), at(10)).title = "Y"  # type: ignore[misc]


def test_events_to_busy_solo_proiezione():
    out = events_to_busy(
        [FixedEvent("A", at(11), at(12)), FixedEvent("B", at(11, 30), at(13))]
    )
    # Nessun merge qui: resta dentro schedule().
    assert out == (TimeWindow(at(11), at(12)), TimeWindow(at(11, 30), at(13)))
    assert events_to_busy(None) == ()
    assert events_to_busy(["xx", None]) == ()


def _sched(items, avail, events):
    return schedule(plan(*items), avail, busy=events_to_busy(events))


def test_evento_in_mezzo_spezza():
    r = _sched(
        [item(1), item(2, pomo=2), item(3)],
        [TimeWindow(at(9), at(15))],
        [FixedEvent("Riunione", at(11), at(12))],
    )
    got = [(s.item.todo_id, s.start, s.end) for s in r.scheduled]
    assert got == [
        (1, at(9), at(9, 30)),
        (2, at(9, 30), at(10, 30)),
        (3, at(10, 30), at(11)),  # first-fit: prima dell'evento
    ]


def test_evento_sposta_dopo():
    r = _sched(
        [item(1, pomo=4)],
        [TimeWindow(at(9), at(15))],
        [FixedEvent("R", at(9, 30), at(12))],
    )
    assert [(s.start, s.end) for s in r.scheduled] == [(at(12), at(14))]


def test_eventi_fuori_prima_dopo_tutto_coperto():
    assert _sched(
        [item(1)], [TimeWindow(at(9), at(17))], [FixedEvent("S", at(18), at(19))]
    ).scheduled
    assert _sched(
        [item(1)], [TimeWindow(at(9), at(17))], [FixedEvent("P", at(7), at(8))]
    ).scheduled
    r = _sched([item(1)], [TimeWindow(at(9), at(17))], [FixedEvent("T", at(8), at(18))])
    assert r.scheduled == () and [i.todo_id for i in r.unscheduled] == [1]


def test_eventi_consecutivi_sovrapposti_e_bordi():
    r = _sched(
        [item(1), item(2)],
        [TimeWindow(at(9), at(17))],
        [FixedEvent("A", at(11), at(12)), FixedEvent("B", at(12), at(13))],
    )
    assert r.busy == (TimeWindow(at(11), at(13)),)
    assert [(s.start, s.end) for s in r.scheduled] == [
        (at(9), at(9, 30)),
        (at(9, 30), at(10)),
    ]
    r = _sched(
        [item(1)],
        [TimeWindow(at(9), at(17))],
        [FixedEvent("A", at(9, 30), at(10)), FixedEvent("B", at(9, 45), at(11))],
    )
    assert [(s.start, s.end) for s in r.scheduled] == [(at(9), at(9, 30))]


def test_evento_a_cavallo_di_mezzanotte_clippato():
    r = _sched(
        [item(1)],
        [TimeWindow(at(9), at(23, 30))],
        [FixedEvent("N", datetime(2026, 9, 10, 22), datetime(2026, 9, 11, 2))],
    )
    assert r.busy == (TimeWindow(at(22), datetime(2026, 9, 11, 0)),)
    assert [(s.start, s.end) for s in r.scheduled] == [(at(9), at(9, 30))]


def test_mandatory_senza_posto_e_dayplan_invariato():
    p = plan(item(1, pomo=8, mandatory=True), item(2))
    before = p.to_legacy()
    r = schedule(
        p,
        [TimeWindow(at(9), at(10))],
        busy=events_to_busy([FixedEvent("R", at(9), at(10))]),
    )
    assert [i.todo_id for i in r.unscheduled] == [1, 2]
    assert r.scheduled == ()
    assert p.to_legacy() == before
    assert schedule(p, [TimeWindow(at(9), at(10))]).scheduled  # busy=() invariato


def test_determinismo():
    args = ([TimeWindow(at(9), at(15))], [FixedEvent("R", at(11), at(12))])
    p = plan(item(1, pomo=2), item(2))
    a = schedule(p, args[0], busy=events_to_busy(args[1]))
    b = schedule(p, args[0], busy=events_to_busy(args[1]))
    assert a == b
