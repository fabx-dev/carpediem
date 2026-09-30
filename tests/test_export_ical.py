"""Equivalenza E1: src/export_ical.py == metodi originali di TodoApp."""

import src.export_ical as ei
from src.models import Priority
from tests.conftest import make_app, make_todo


def _cases():
    return [
        make_todo("Con ora", todo_id=1, due="2026-01-02 09:30", project="work"),
        make_todo("Giorno intero", todo_id=2, due="2026-01-03"),
        make_todo(
            "Speciali ;,\\n",
            todo_id=3,
            due="2026-01-04 10:00",
            tags=["a", "b"],
            notes="riga1\nriga2",
        ),
        make_todo("Alta", todo_id=4, due="2026-01-05", priority=Priority.HIGH),
    ]


def test_escape_equivalente():
    app = make_app([])
    for raw in ["a;b,c\\d\ne", "Progetto: x", "", "09:30"]:
        assert app._ical_escape(raw) == ei.ical_escape(raw)


def test_event_lines_equivalenti():
    app = make_app([])
    for t in _cases():
        parts = (t.due or "").split()
        date_part = parts[0]
        time_part = (
            parts[1]
            if len(parts) >= 2 and len(parts[1]) == 5 and parts[1][2] == ":"
            else ""
        )
        assert app._ical_event_lines(
            t, date_part, time_part, "STAMP"
        ) == ei.ical_event_lines(t, date_part, time_part, "STAMP")


def test_event_lines_contenuto():
    t = make_todo("Con ora", todo_id=1, due="2026-01-02 09:30", project="work")
    lines = ei.ical_event_lines(t, "2026-01-02", "09:30", "STAMP")
    assert lines[0] == "BEGIN:VEVENT" and lines[-1] == "END:VEVENT"
    assert "SUMMARY:Con ora" in lines
    assert "DTSTART:20260102T093000" in lines
    allday = ei.ical_event_lines(
        make_todo("Giorno intero", todo_id=2, due="2026-01-03"),
        "2026-01-03",
        "",
        "STAMP",
    )
    assert "DTSTART;VALUE=DATE:20260103" in allday
    assert "DTEND;VALUE=DATE:20260104" in allday
