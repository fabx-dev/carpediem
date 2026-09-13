"""Agenda cronologica ed export iCal."""

from datetime import datetime, timedelta

import src.app as app_module
from src.lang import T
from src.models import Priority
from tests.conftest import make_app, make_todo, run, screen_texts


def test_agenda_mostra_sezioni_temporali(tmp_files):
    async def t():
        today = datetime.now().date()
        app = make_app(
            [
                make_todo(
                    "Scaduto", due=(today - timedelta(days=1)).strftime("%Y-%m-%d")
                ),
                make_todo("Oggi", due=today.strftime("%Y-%m-%d 09:00")),
                make_todo(
                    "Domani", due=(today + timedelta(days=1)).strftime("%Y-%m-%d")
                ),
                make_todo(
                    "Importante",
                    due="",
                    priority=Priority.HIGH,
                ),
            ]
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_view_agenda()
            await pilot.pause()
            text = screen_texts(app.screen)
            assert T("agenda_overdue") in text
            assert T("agenda_today") in text
            assert T("agenda_tomorrow") in text
            assert T("agenda_important") in text
            assert "Scaduto" in text and "Oggi" in text and "Importante" in text

    run(t())


def test_export_ical_scrive_eventi_con_scadenza(tmp_files, monkeypatch):
    async def t():
        monkeypatch.setattr(app_module, "_home", lambda: tmp_files)
        app = make_app(
            [
                make_todo("Con ora", todo_id=1, due="2026-01-02 09:30", project="work"),
                make_todo("Giorno intero", todo_id=2, due="2026-01-03"),
                make_todo("Fatto", todo_id=3, due="2026-01-04", done=True),
                make_todo("Senza data", todo_id=4, due=""),
            ]
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_export_ical()
            await pilot.pause()
        files = sorted(
            (tmp_files / "CarpeDiem_screenshots").glob("carpediem_calendar_*.ics")
        )
        assert len(files) == 1
        data = files[0].read_text(encoding="utf-8")
        assert "BEGIN:VCALENDAR" in data
        assert data.count("BEGIN:VEVENT") == 2
        assert "SUMMARY:Con ora" in data
        assert "DTSTART:20260102T093000" in data
        assert "SUMMARY:Giorno intero" in data
        assert "DTSTART;VALUE=DATE:20260103" in data
        assert "Fatto" not in data and "Senza data" not in data

    run(t())
