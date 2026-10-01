"""Timezone/DST per planner e Outlook (P1 §11).

Convenzione del repo: wall-time naive. Questi test fissano che le
conversioni non siano ambigue su DST, mezzanotte, adiacenza ed eventi
tutto-il-giorno, su Europe/Rome, UTC e America/New_York.
"""

from datetime import datetime

import src.integrations.outlook as o
import src.planner.scheduler as sched
from src.planner.models import TimeWindow


def _item(title, start, end, tz="Europe/Rome", show_as="busy", allday=False):
    return {
        "subject": title,
        "start": {"dateTime": start, "timeZone": tz},
        "end": {"dateTime": end, "timeZone": tz},
        "showAs": show_as,
        "isAllDay": allday,
    }


def _payload(items):
    return {"value": items}


def test_dst_primavera_roma_aware():
    # 2026-03-29: alle 02:00 -> 03:00. Aware con offset: conversione esatta.
    items = [
        _item("prima", "2026-03-29T01:30:00+01:00", "2026-03-29T01:45:00+01:00"),
        _item("dopo", "2026-03-29T03:30:00+02:00", "2026-03-29T04:00:00+02:00"),
    ]
    events, _allday, skipped = o.parse_graph_events(_payload(items), "2026-03-29")
    assert not skipped
    assert [(e.title, e.start, e.end) for e in events] == [
        ("prima", datetime(2026, 3, 29, 1, 30), datetime(2026, 3, 29, 1, 45)),
        ("dopo", datetime(2026, 3, 29, 3, 30), datetime(2026, 3, 29, 4, 0)),
    ]


def test_dst_autunno_roma_ora_ambigua_resta_deterministico():
    # 2026-10-25: ora 02:00-03:00 ambigua in wall-time; con offset e' esatta.
    items = [
        _item("estiva", "2026-10-25T02:30:00+02:00", "2026-10-25T02:45:00+02:00"),
        _item("solare", "2026-10-25T02:30:00+01:00", "2026-10-25T02:45:00+01:00"),
    ]
    first = o.parse_graph_events(_payload(items), "2026-10-25")
    second = o.parse_graph_events(_payload(items), "2026-10-25")
    assert first == second
    assert len(first[0]) == 2


def test_fusi_utc_e_new_york():
    items = [
        _item(
            "utc", "2026-06-01T09:00:00+00:00", "2026-06-01T10:00:00+00:00", tz="UTC"
        ),
        _item(
            "ny",
            "2026-06-01T09:00:00-04:00",
            "2026-06-01T10:00:00-04:00",
            tz="Eastern Standard Time",
        ),
    ]
    ev_utc, _, _ = o.parse_graph_events(_payload([items[0]]), "2026-06-01", tz="UTC")
    assert (ev_utc[0].start, ev_utc[0].end) == (
        datetime(2026, 6, 1, 9, 0),
        datetime(2026, 6, 1, 10, 0),
    )
    ev_ny, _, _ = o.parse_graph_events(
        _payload([items[1]]), "2026-06-01", tz="America/New_York"
    )
    assert (ev_ny[0].start, ev_ny[0].end) == (
        datetime(2026, 6, 1, 9, 0),
        datetime(2026, 6, 1, 10, 0),
    )


def test_evento_a_cavallo_di_mezzanotte_interseca_entrambi_i_giorni():
    items = [_item("notte", "2026-06-01T23:00:00", "2026-06-02T01:00:00")]
    assert len(o.parse_graph_events(_payload(items), "2026-06-01")[0]) == 1
    assert len(o.parse_graph_events(_payload(items), "2026-06-02")[0]) == 1
    assert o.parse_graph_events(_payload(items), "2026-06-03")[0] == []


def test_eventi_adiacenti_non_si_sovrappongono():
    items = [
        _item("a", "2026-06-01T09:00:00", "2026-06-01T10:00:00"),
        _item("b", "2026-06-01T10:00:00", "2026-06-01T11:00:00"),
    ]
    events, _, skipped = o.parse_graph_events(_payload(items), "2026-06-01")
    assert not skipped
    assert events[0].end == events[1].start == datetime(2026, 6, 1, 10, 0)


def test_allday_riga_informativa_mai_busy():
    items = [_item("ferie", "2026-06-01T00:00:00", "2026-06-02T00:00:00", allday=True)]
    events, allday, _ = o.parse_graph_events(_payload(items), "2026-06-01")
    assert events == []
    assert allday == ["ferie"]
    assert sched.events_to_busy(events) == ()


def test_overlapping_resta_ordinato_e_deterministico():
    items = [
        _item("b", "2026-06-01T09:30:00", "2026-06-01T10:30:00"),
        _item("a", "2026-06-01T09:00:00", "2026-06-01T10:00:00"),
    ]
    first = o.parse_graph_events(_payload(items), "2026-06-01")
    assert [e.title for e in first[0]] == ["a", "b"]
    assert first == o.parse_graph_events(_payload(items), "2026-06-01")


def test_politica_core_naive_su_transizione_dst():
    """Limite dichiarato (scheduler docstring): il core somma wall-time
    naive anche sull'ora mancante del 2026-03-29 a Roma (02:00 -> 03:00):
    01:30 + 30min = 02:00 naive (1h reale). Pinnato per impedire fix
    ingenui verso aware (romperebbero i dati); il bordo Outlook resta
    l'unico punto tz-aware."""
    from datetime import timedelta

    from src.planner.models import DayPlan, PlanItem

    plan = DayPlan(
        day=datetime(2026, 3, 29).date(), planned=(PlanItem(1, 10, (), 1, False),)
    )
    avail = [TimeWindow(datetime(2026, 3, 29, 1, 30), datetime(2026, 3, 29, 4, 0))]
    (slot,) = sched.schedule(plan, avail, ()).scheduled
    assert (slot.start, slot.end) == (
        datetime(2026, 3, 29, 1, 30),
        datetime(2026, 3, 29, 2, 0),
    )
    assert slot.end - slot.start == timedelta(minutes=30)
