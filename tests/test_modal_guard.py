"""Modali: le action App sono inerti sotto i dialoghi; click handler esistenti."""

from datetime import datetime, timedelta

from src.lang import T
from tests.conftest import make_app, make_todo, run, screen_texts


def test_check_action_blocca_tutto_sotto_modale(tmp_files):
    async def t():
        app = make_app([make_todo("A", todo_id=1)])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app.check_action("new_todo", ()) is not False
            assert app.check_action("quit", ()) is not False
            app.action_view_stats()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "StatsScreen"
            for name in (
                "new_todo",
                "delete_todo",
                "quit",
                "open_menu",
                "search_todos",
            ):
                assert app.check_action(name, ()) is False, name
            await pilot.press("n")
            await pilot.pause()
            assert type(app.screen).__name__ == "StatsScreen"
            await pilot.press("escape")
            await pilot.pause()
            assert type(app.screen).__name__ != "StatsScreen"
            assert app.check_action("new_todo", ()) is not False

    run(t())


def test_tab_naviga_anche_sotto_modale(tmp_files):
    """Il guard non deve bloccare focus_next/focus_previous di Textual."""

    async def t():
        app = make_app([make_todo("A", todo_id=1)])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_choose_theme()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "ThemeListScreen"
            assert app.check_action("focus_next", ()) is not False
            buttons = list(app.screen.query("#theme-list Button"))
            assert len(buttons) >= 2
            for _ in range(len(buttons) + 2):
                if getattr(app.screen.focused, "id", None) == "theme-close":
                    break
                await pilot.press("tab")
                await pilot.pause()
            assert getattr(app.screen.focused, "id", None) == "theme-close"

    run(t())


def test_calendar_day_apre_giorno_sopra_calendario(tmp_files):
    """open_day e' allowlistata: modale-sopra-modale calendario->giorno funziona.

    Nota: i link [@click] negli Static non vengono dispensati da Textual
    (solo stile hover), quindi il click si testa per parti: target del link
    esistente + gate aperto + handler che impila DayScreen sopra CalendarScreen.
    """

    async def t():
        app = make_app(
            [make_todo("A", todo_id=1, due=datetime.now().strftime("%Y-%m-%d"))]
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_view_calendar()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "CalendarScreen"
            assert app.check_action("open_day", ()) is not False
            today = datetime.now().date()
            app.action_open_day(today.year, today.month, today.day)
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "DayScreen"

    run(t())


def test_calendar_day_click_punta_a_handler_reale(tmp_files):
    """Il calendario NON usa piu' il markup [@click] (morto in Textual 3.x):
    il giorno deve risolversi via CalendarGrid._day_at verso l'action reale."""

    async def t():
        app = make_app(
            [make_todo("A", todo_id=1, due=datetime.now().strftime("%Y-%m-%d"))]
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_view_calendar()
            await pilot.pause()
            await pilot.pause()
            grid = screen_texts(app.screen)
            assert "app.action_open_day(" not in grid  # markup morto: assente
            assert callable(getattr(app, "action_open_day"))
            import calendar as cal

            today = datetime.now()
            widget = app.screen.query_one("#calendar-grid")
            weeks = cal.Calendar(firstweekday=0).monthdayscalendar(
                today.year, today.month
            )
            wi = next(w for w, days in enumerate(weeks) if today.day in days)
            di = weeks[wi].index(today.day)
            # la mappa riga/colonna -> giorno funziona (y=0 header -> None)
            assert widget._day_at(di * 6 + 2, 1 + wi * 2) == today.day
            assert widget._day_at(di * 6 + 2, 0) is None

    run(t())


def test_pomodoro_bar_click_puntano_a_handler_reali(tmp_files):
    """La barra NON usa piu' il markup [@click] (morto in Textual 3.x): gli
    hint devono essere parole localizzate mappate a handler reali esistenti."""
    app = make_app([make_todo("A", todo_id=1)])
    app.focus_task_id = 1
    app.focus_total_secs = 25 * 60
    app.focus_end = datetime.now() + timedelta(minutes=25)
    app.focus_phase = "focus"
    app.focus_paused_secs = None
    text = app._pomodoro_text()
    assert "app.action_start_pomodoro" not in text  # markup morto: assente
    import src.app as app_mod

    bar = app_mod.PomodoroBar("")
    for word, action in bar._hints():
        assert callable(getattr(app, action)), action
        if word not in ("completa", "salta"):
            assert word in text, word
    # "completa"/"salta" sono alternati per fase: esattamente uno nel testo
    assert ("completa" in text) != ("salta" in text)


def test_tpl_empty_hint_minuscola(tmp_files):
    assert "[b]n[/b]" in T("tpl_empty")
    assert "[b]N[/b]" not in T("tpl_empty")
