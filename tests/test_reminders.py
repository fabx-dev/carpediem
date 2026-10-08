"""Test reminder scadenze con orario + beep (file isolati)."""

import asyncio
from datetime import datetime, timedelta

import carpediem.main as m
from tests.conftest import make_app, make_todo


def _due_in(minutes: int) -> str:
    return (datetime.now() + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M")


def test_solo_con_orario_una_tantum(tmp_files, capsys):
    app = make_app(
        [
            make_todo(" VICINO", due=_due_in(5), todo_id=1),
            make_todo("LONTANO", due=_due_in(120), todo_id=2),
            make_todo("SENZA ORA", due=datetime.now().strftime("%Y-%m-%d"), todo_id=3),
            make_todo("FATTO", due=_due_in(5), done=True, todo_id=4),
        ]
    )
    app.config["reminder_min"] = 10
    app.config["sounds"] = True
    app._check_reminders()
    assert (1, app.todos[0].due.strip()) in app._reminded
    assert len(app._reminded) == 1
    out = capsys.readouterr().out
    assert out.count("\a") == 3
    # seconda passata: niente doppioni, niente beep
    app._check_reminders()
    assert len(app._reminded) == 1
    assert capsys.readouterr().out == ""


def test_reminder_persistente_fino_al_click(tmp_files):
    """Il toast del reminder usa timeout lungo (default Textual: 5 s)."""
    from carpediem.app import REMINDER_TOAST_TIMEOUT

    assert REMINDER_TOAST_TIMEOUT >= 600
    app = make_app([make_todo("VICINO", due=_due_in(5), todo_id=1)])
    app.config["reminder_min"] = 10
    app.config["sounds"] = False
    calls = []
    app.notify = lambda msg, **kw: calls.append(kw)
    app._check_reminders()
    assert len(calls) == 1
    assert calls[0].get("timeout") == REMINDER_TOAST_TIMEOUT


def test_vecchio_e_spento_e_scaduto(tmp_files, capsys):
    app = make_app(
        [
            make_todo(
                "IERI",
                due=(datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M"),
                todo_id=1,
            )
        ]
    )
    app._check_reminders()
    assert app._reminded == set()  # ieri: nessun toast
    app.todos = [make_todo("X", due=_due_in(5), todo_id=2)]
    app.config["reminder_min"] = 0
    app._check_reminders()
    assert app._reminded == set()
    app.config["reminder_min"] = 10
    app.config["sounds"] = False
    app._check_reminders()
    assert len(app._reminded) == 1
    assert capsys.readouterr().out == ""  # toast si, beep no


def test_beep_pomodoro(tmp_files):
    async def t():
        app = make_app([make_todo("F")])
        app.config["sounds"] = True
        beeps = []
        app._beep = lambda times=1: beeps.append(times)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("o")
            await pilot.pause()
            await pilot.pause()
            await pilot.press("x")  # completa focus -> 1 beep + pausa auto
            await pilot.pause()
            await pilot.pause()
            assert app.focus_phase == "short"
            assert beeps == [1], beeps
            app.focus_end = datetime.now() - timedelta(seconds=1)
            app._tick_focus()  # finisce la pausa -> 2 beep
            await pilot.pause()
            assert app.focus_task_id is None
            assert beeps == [1, 2], beeps

    asyncio.run(t())


def test_settings_reminder_sounds(tmp_files):
    import json

    async def t():
        from textual.widgets import Input, Select

        app = make_app([make_todo("A")])
        async with app.run_test(size=(130, 55)) as pilot:
            await pilot.pause()
            app.action_open_settings()
            await pilot.pause()
            await pilot.pause()
            app.screen.query_one("#set-reminder", Input).value = "15"
            app.screen.query_one("#set-sounds", Select).value = False
            await pilot.press("ctrl+enter")
            await pilot.pause()
            await pilot.pause()
            assert app.config["reminder_min"] == 15
            assert app.config["sounds"] is False
            saved = json.loads(m.CONFIG_FILE.read_text(encoding="utf-8"))
            assert saved["reminder_min"] == 15 and saved["sounds"] is False

    asyncio.run(t())
