"""Adapter Outlook B1: parsing puro del JSON calendarView (niente rete/auth).

Fixture inline anonime (mai dati reali): coprono base, filtri free/all-day,
offset aware, zone ignote (fail-closed), overnight, cap/troncamento e i
guardrail di sicurezza (scope/endpoint congelati, niente import di rete).
"""

import pathlib

from src.integrations import (
    GRAPH_BASE_URL,
    GRAPH_SCOPES,
    LOGIN_AUTHORITY,
    parse_graph_events,
)

DAY = "2026-09-23"
ROM = "W. Europe Standard Time"


def _ev(subject, start, end, **kw):
    item = {
        "subject": subject,
        "start": {"dateTime": start, "timeZone": ROM},
        "end": {"dateTime": end, "timeZone": ROM},
        "showAs": "busy",
        "isAllDay": False,
    }
    item.update(kw)
    return item


def _payload(items):
    return {"value": items}


def test_base_due_eventi_ordinati():
    events, allday, skipped = parse_graph_events(
        _payload(
            [
                _ev("B", f"{DAY}T11:00:00.0000000", f"{DAY}T12:00:00.0000000"),
                _ev("A", f"{DAY}T09:00:00.0000000", f"{DAY}T09:30:00.0000000"),
            ]
        ),
        DAY,
    )
    assert [e.title for e in events] == ["A", "B"]
    assert allday == []
    assert skipped == []
    assert events[0].start.strftime("%H:%M") == "09:00"
    assert events[1].end.strftime("%H:%M") == "12:00"


def test_free_e_allday_scartati_con_titolo():
    events, allday, skipped = parse_graph_events(
        _payload(
            [
                _ev("Focus mio", f"{DAY}T09:00:00", f"{DAY}T10:00:00", showAs="free"),
                _ev("Ferragosto", f"{DAY}T00:00:00", f"{DAY}T23:59:00", isAllDay=True),
                _ev("Daily", f"{DAY}T10:00:00", f"{DAY}T10:15:00"),
            ]
        ),
        DAY,
    )
    assert [e.title for e in events] == ["Daily"]
    assert allday == ["Ferragosto"]
    assert skipped == ["Focus mio"]


def test_aware_con_offset_convertito_a_roma():
    # 09:00+02:00 = 09:00 wall-time Roma (settembre, DST).
    events, _, _ = parse_graph_events(
        _payload([_ev("Call", f"{DAY}T09:00:00+02:00", f"{DAY}T10:00:00+02:00")]),
        DAY,
    )
    assert events[0].start.strftime("%H:%M") == "09:00"


def test_naive_zona_diversa_convertito():
    # 09:00 New York = 15:00 Roma.
    events, _, _ = parse_graph_events(
        _payload(
            [
                {
                    "subject": "NY",
                    "start": {
                        "dateTime": f"{DAY}T09:00:00",
                        "timeZone": "Eastern Standard Time",
                    },
                    "end": {
                        "dateTime": f"{DAY}T10:00:00",
                        "timeZone": "Eastern Standard Time",
                    },
                    "showAs": "busy",
                }
            ]
        ),
        DAY,
    )
    assert events[0].start.strftime("%H:%M") == "15:00"


def test_zona_sconosciuta_fail_closed():
    events, allday, skipped = parse_graph_events(
        _payload(
            [
                {
                    "subject": "X",
                    "start": {"dateTime": f"{DAY}T09:00:00", "timeZone": "Atlantis"},
                    "end": {"dateTime": f"{DAY}T10:00:00", "timeZone": "Atlantis"},
                    "showAs": "busy",
                }
            ]
        ),
        DAY,
    )
    assert events == [] and skipped == ["X"]


def test_overnight_tenuto_altro_giorno_ignorato():
    events, allday, skipped = parse_graph_events(
        _payload(
            [
                _ev("Notte", f"{DAY}T23:00:00", "2026-09-24T01:00:00"),
                _ev("Ieri", "2026-09-22T09:00:00", "2026-09-22T10:00:00"),
                _ev("Rotto", f"{DAY}T10:00:00", f"{DAY}T09:00:00"),
                _ev("Senza fine", f"{DAY}T10:00:00", ""),
            ]
        ),
        DAY,
    )
    assert [e.title for e in events] == ["Notte"]
    assert sorted(skipped) == ["Rotto", "Senza fine"]


def test_cap_e_troncamento():
    items = [
        _ev(
            f"E{i:02d}",
            f"{DAY}T{(8 + i // 60):02d}:{i % 60:02d}:00",
            f"{DAY}T{(8 + (i + 1) // 60):02d}:{(i + 1) % 60:02d}:00",
        )
        for i in range(35)
    ]
    events, _, _ = parse_graph_events(_payload(items), DAY)
    assert len(events) == 30
    long_ev, _, skipped = parse_graph_events(
        _payload([_ev("T" * 200, f"{DAY}T09:00:00", f"{DAY}T10:00:00")]), DAY
    )
    assert len(long_ev[0].title) == 120 and skipped == []


def test_payload_malformato_mai_solleva():
    assert parse_graph_events(None, DAY) == ([], [], [])
    assert parse_graph_events({"value": "no"}, DAY) == ([], [], [])
    assert parse_graph_events({"value": [None, 42, {}]}, DAY)[:2] == ([], [])
    assert parse_graph_events(_payload([]), "non-una-data") == ([], [], [])
    assert parse_graph_events(_payload([]), DAY, tz="Atlantis") == ([], [], [])


def test_scope_congelato_solo_calendars_read():
    assert GRAPH_SCOPES == ("Calendars.Read",)
    assert GRAPH_BASE_URL == "https://graph.microsoft.com/v1.0"
    assert LOGIN_AUTHORITY.startswith("https://login.microsoftonline.com/")
    assert "common" not in LOGIN_AUTHORITY


def test_niente_rete_nell_adapter():
    src = pathlib.Path("src/integrations/outlook.py").read_text(encoding="utf-8")
    for mod in ("msal", "httpx", "requests", "urllib", "aiohttp"):
        assert f"import {mod}" not in src, f"rete vietata in B1: {mod}"
    assert "http://" not in src
