"""Link cliccabili reali: barra pomodoro e griglia calendario.

Textual 3.x non dispatcha piu' le azioni-in-markup [@click=...] (meta
assente dai segmenti, verificato sperimentalmente): barra e calendario
risolvono i click con handler reali mappando le coordinate — verificati
qui con pilot.click (che passa coordinate vere all'handler)."""

from datetime import datetime, timedelta

import src.app as app_mod
import src.screens.views as views_mod
from src.models import TodoItem
from src.storage import load_todos
from tests.conftest import run


def _label_text(c) -> str:
    labels = c.query("Label")
    if not labels:
        return ""
    w = labels.first()
    content = getattr(w, "content", None)
    if content is None:
        content = getattr(w, "renderable", "")
    return str(content)


def _seed_task(title="Task A", stima=1):
    app0 = app_mod.TodoApp()
    app0.store.add(TodoItem(title=title, todo_id=None, stima_pomo=stima))
    app0.store.commit()
    app = app_mod.TodoApp()
    app.todos = load_todos()
    return app


def _click_word(app, pilot, word):
    """Click sulla parola cercata nella barra (ultima occorrenza: gli hint
    sono sempre in coda al testo)."""
    bar = app.query_one("#pomodoro-bar")
    plain = bar.render().plain
    pos = plain.rfind(word)
    assert pos >= 0, word
    return pilot.click("#pomodoro-bar", offset=(2 + pos + 1, 1))


# --- barra pomodoro ----------------------------------------------------------


def test_bar_click_apri_popup(tmp_files):
    async def t():
        app = _seed_task()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("o")
            await pilot.pause()
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()
            await _click_word(app, pilot, "apri")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "PomodoroScreen"

    run(t())


def test_bar_click_pausa_e_riprendi(tmp_files):
    async def t():
        app = _seed_task()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("o")
            await pilot.pause()
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()
            await _click_word(app, pilot, "pausa/riprendi")
            await pilot.pause()
            await pilot.pause()
            assert app.focus_paused_secs is not None
            await _click_word(app, pilot, "pausa/riprendi")
            await pilot.pause()
            await pilot.pause()
            assert app.focus_paused_secs is None

    run(t())


def test_bar_click_completa_credita_e_pausa(tmp_files):
    async def t():
        app = _seed_task()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("o")
            await pilot.pause()
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()
            await _click_word(app, pilot, "completa")
            await pilot.pause()
            await pilot.pause()
            assert load_todos()[0].pomodoros == 1
            assert app.focus_phase in ("short", "long")  # pausa avviata

    run(t())


def test_bar_click_salta_nella_pausa(tmp_files):
    async def t():
        app = _seed_task()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("o")
            await pilot.pause()
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()
            await _click_word(app, pilot, "completa")  # avvia la pausa
            await pilot.pause()
            await pilot.pause()
            await _click_word(app, pilot, "salta")  # salta la pausa
            await pilot.pause()
            await pilot.pause()
            assert app.focus_task_id is None
            assert app.focus_phase is None

    run(t())


def test_bar_click_fuori_dai_hint_inerte(tmp_files):
    async def t():
        app = _seed_task()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("o")
            await pilot.pause()
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()
            before_pomo = load_todos()[0].pomodoros
            before_paused = app.focus_paused_secs is not None
            # zona titolo/timer (prima degli hint): nessuna azione
            await pilot.click("#pomodoro-bar", offset=(15, 1))
            await pilot.pause()
            await pilot.pause()
            assert load_todos()[0].pomodoros == before_pomo
            assert (app.focus_paused_secs is not None) == before_paused
            assert type(app.screen).__name__ != "PomodoroScreen"

    run(t())


# --- griglia calendario ------------------------------------------------------


def _seed_due_today_and_later():
    today = datetime.now()
    app0 = app_mod.TodoApp()
    app0.store.add(
        TodoItem(title="Oggi", todo_id=None, due=f"{today.strftime('%Y-%m-%d')} 10:00")
    )
    later = today + timedelta(days=3)
    app0.store.add(
        TodoItem(title="Dopo", todo_id=None, due=f"{later.strftime('%Y-%m-%d')} 10:00")
    )
    app0.store.commit()


def test_calendario_click_giorno_oggi(tmp_files):
    async def t():
        _seed_due_today_and_later()
        app = app_mod.TodoApp()
        app.todos = load_todos()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_view_calendar()
            await pilot.pause()
            await pilot.pause()
            grid = app.screen.query_one("#calendar-grid")
            assert isinstance(grid, views_mod.CalendarGrid)
            today = datetime.now().date()
            import calendar as cal

            weeks = cal.Calendar(firstweekday=0).monthdayscalendar(
                today.year, today.month
            )
            wi = next(w for w, days in enumerate(weeks) if today.day in days)
            di = weeks[wi].index(today.day)
            await pilot.click("#calendar-grid", offset=(di * 6 + 2, 1 + wi * 2))
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "DayScreen"

    run(t())


def test_calendario_click_header_inerte(tmp_files):
    async def t():
        _seed_due_today_and_later()
        app = app_mod.TodoApp()
        app.todos = load_todos()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_view_calendar()
            await pilot.pause()
            await pilot.pause()
            # riga 0 = intestazione giorni: nessuna azione
            await pilot.click("#calendar-grid", offset=(2, 0))
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "CalendarScreen"
            # cella vuota (giorno 0, inizio fine mese): nessuna azione
            import calendar as cal

            today = datetime.now()
            weeks = cal.Calendar(firstweekday=0).monthdayscalendar(
                today.year, today.month
            )
            empty = next(
                (
                    (w, p)
                    for w, days in enumerate(weeks)
                    for p, d in enumerate(days)
                    if d == 0
                ),
                None,
            )
            if empty:
                w, p = empty
                await pilot.click("#calendar-grid", offset=(p * 6 + 2, 1 + w * 2))
                await pilot.pause()
                await pilot.pause()
                assert type(app.screen).__name__ == "CalendarScreen"

    run(t())
