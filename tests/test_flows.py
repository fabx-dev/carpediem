"""Test flussi UI via Textual pilot (file isolati da conftest)."""

from datetime import datetime, timedelta

from textual.widgets import Input

import src.app as app_module
import src.main as m
from tests.conftest import make_app, make_todo, run, screen_texts


def test_kanban_visibile_e_toggle(tmp_files):
    async def t():
        app = make_app(
            [
                make_todo("A", todo_id=1, due="2026-01-10"),
                make_todo("B", todo_id=2, due="2026-12-31"),
            ]
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            bar = app.query_one("#pomodoro-bar")
            assert bar.has_class("hidden")
            kb = app.query_one("#kanban-bar")
            order = (
                ["grafico", "testo", "nascosto"]
                if app_module.PlotextPlot is not None
                else ["testo", "nascosto"]
            )
            start = app._kanban_mode()
            assert start in order
            assert kb.has_class("hidden") == (start != "testo")
            idx = order.index(start)
            for step in range(1, len(order) + 1):
                await pilot.press("b")
                await pilot.pause()
                expected = order[(idx + step) % len(order)]
                assert app._kanban_mode() == expected
                assert kb.has_class("hidden") == (expected != "testo")
                assert app.config["kanban_visible"] == (expected != "nascosto")

    run(t())


def test_dettaglio_singolo_e_chiusura(tmp_files):
    async def t():
        app = make_app([make_todo("A"), make_todo("B", todo_id=2)])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            table = app.query_one("#todo-table")
            await pilot.click(table, offset=(5, 1))
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "DetailScreen"
            assert len(app.screen_stack) == 2
            await pilot.click(app.screen.query_one("#detail-close"))
            await pilot.pause()
            await pilot.pause()
            assert len(app.screen_stack) == 1
            # riclick stessa riga: resta singolo
            await pilot.click(table, offset=(5, 1))
            await pilot.pause()
            await pilot.pause()
            assert len(app.screen_stack) == 2

    run(t())


def test_modifica_dal_dettaglio(tmp_files):
    async def t():
        app = make_app([make_todo("A")])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_view_detail()
            await pilot.pause()
            await pilot.pause()
            await pilot.click(app.screen.query_one("#detail-edit"))
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "TodoFormScreen"
            app.screen.query_one("#title-input", Input).value = "A2"
            await pilot.press("ctrl+enter")
            await pilot.pause()
            await pilot.pause()
            assert app.todos[0].title == "A2"
            assert type(app.screen).__name__ == "DetailScreen"

    run(t())


def test_template_crud(tmp_files):
    async def t():
        app = make_app([make_todo("A")])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            # usa
            app.action_new_from_template()
            await pilot.pause()
            await pilot.pause()
            n0 = len(app.todos)
            await pilot.click(app.screen.query_one("#tpl-use-0"))
            await pilot.pause()
            await pilot.pause()
            assert len(app.todos) == n0 + 5
            # crea
            app.action_new_from_template()
            await pilot.pause()
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "TemplateCreateScreen"
            app.screen.query_one("#tplc-name", Input).value = "T"
            from textual.widgets import TextArea

            app.screen.query_one("#tplc-tasks", TextArea).text = "Uno\nDue"
            await pilot.press("ctrl+enter")
            await pilot.pause()
            await pilot.pause()
            assert "T" in app.templates
            await pilot.press("escape")
            await pilot.pause()
            # elimina con conferma
            app.action_new_from_template()
            await pilot.pause()
            await pilot.pause()
            await pilot.click(app.screen.query_one("#tpl-del-0"))
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "ConfirmScreen"
            await pilot.click(app.screen.query_one("#yes-btn"))
            await pilot.pause()
            await pilot.pause()
            assert "Nuovo cliente" not in app.templates

    run(t())


def test_pomodoro_ciclo(tmp_files):
    async def t():
        app = make_app([make_todo("F")])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("o")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "PomodoroScreen"
            assert app.focus_phase == "focus"
            await pilot.press("x")
            await pilot.pause()
            await pilot.pause()
            assert app.focus_phase == "short" and app.pomo_cycle == 1
            assert app.todos[0].pomodoros == 1
            await pilot.press("escape")
            await pilot.pause()
            # pausa globale in break
            await pilot.press("O")
            await pilot.pause()
            assert app.focus_paused_secs is not None
            await pilot.press("O")
            await pilot.pause()
            assert app.focus_paused_secs is None
            # salta break
            await pilot.press("X")
            await pilot.pause()
            assert app.focus_task_id is None and app.pomo_cycle == 1

    run(t())


def test_pomodoro_pausa_lunga_ogni_4(tmp_files):
    async def t():
        app = make_app([make_todo("F")])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            for _ in range(4):
                app.focus_task_id = None
                await pilot.press("o")
                await pilot.pause()
                await pilot.press("escape")
                await pilot.pause()
                app._pomodoro_done()
                await pilot.pause()
            assert app.pomo_cycle == 4
            assert app.focus_phase == "long"
            assert app.focus_total_secs == 15 * 60

    run(t())


def test_ricerca_e_filtri(tmp_files):
    async def t():
        app = make_app(
            [
                make_todo("Dentista", project="casa", tags=["x"]),
                make_todo("Spesa", todo_id=2),
            ]
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("/")
            await pilot.pause()
            assert type(app.screen).__name__ == "SearchScreen"
            assert app.screen.query_one("#search-input", Input).has_focus
            for ch in "dent":
                await pilot.press(ch)
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert app.filter_search == "dent"
            assert len(app._row_map) == 1
            app.action_clear_filters()
            assert app.filter_search == "" and len(app._row_map) == 2
            app.action_filter_todos()
            assert app.filter_state == "attivo"  # da None il ciclo riparte

    run(t())


def test_esc_pulisce_ricerca_attiva(tmp_files):
    """Esc sulla home pulisce la SOLA ricerca (altri filtri intatti);
    a ricerca vuota e' no-op, sotto modale resta inerte."""

    async def t():
        app = make_app(
            [
                make_todo("Dentista", project="casa", tags=["x"]),
                make_todo("Spesa", todo_id=2),
            ]
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("/")
            await pilot.pause()
            for ch in "dent":
                await pilot.press(ch)
            await pilot.press("enter")
            await pilot.pause()
            assert app.filter_search == "dent"
            assert len(app._row_map) == 1
            await pilot.press("escape")
            await pilot.pause()
            assert app.filter_search == ""
            assert len(app._row_map) == 2
            # Gli altri filtri non si toccano: tag attivo + ricerca -> Esc
            # pulisce solo la ricerca.
            app.filter_tag = "x"
            app.filter_search = "dent"
            app._populate_table()
            assert len(app._row_map) == 1
            await pilot.press("escape")
            await pilot.pause()
            assert app.filter_search == ""
            assert app.filter_tag == "x"
            assert len(app._row_map) == 1  # solo Dentista ha il tag x
            # No-op a ricerca vuota: nessun crash, tabella invariata.
            app.filter_tag = None
            app._populate_table()
            assert len(app._row_map) == 2
            await pilot.press("escape")
            await pilot.pause()
            assert app.filter_search == "" and len(app._row_map) == 2
            # Sotto modale Esc chiude senza pulire (guard).
            app.filter_search = "dent"
            app._populate_table()
            await pilot.press("/")
            await pilot.pause()
            assert type(app.screen).__name__ == "SearchScreen"
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ != "SearchScreen"  # chiusa
            assert app.filter_search == "dent"

    run(t())


def test_clear_filters_resetta_anche_config(tmp_files):
    async def t():
        app = make_app([make_todo("A")])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_filter_todos()
            assert app.filter_state == "in_sospeso"
            assert app.config["filter_state"] == "in_sospeso"
            app.action_clear_filters()
            assert app.filter_state is None
            assert app.config["filter_state"] is None
            assert m.load_config().get("filter_state") is None

    run(t())


def test_stats_conteggi_e_streak(tmp_files):
    async def t():
        today = datetime.now().date()

        def ds(o):
            return (today - timedelta(days=o)).strftime("%Y-%m-%d")

        app = make_app(
            [
                make_todo("a", done=True, completed_at=ds(0) + " 10:00"),
                make_todo("b", todo_id=2, done=True, completed_at=ds(1) + " 10:00"),
            ]
        )
        async with app.run_test(size=(130, 55)) as pilot:
            await pilot.pause()
            app.action_view_stats()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "StatsScreen"
            content = screen_texts(app.screen)
            assert "Serie:" in content and "Obiettivo oggi:" in content
            await pilot.press("escape")
            await pilot.pause()

    run(t())


def test_import_csv_e_archivio(tmp_files):
    import csv

    async def t():
        app = make_app([make_todo("Fatto", done=True, completed_at="2026-09-01 10:00")])
        async with app.run_test(size=(130, 55)) as pilot:
            await pilot.pause()
            path = tmp_files / "imp.csv"
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["id", "titolo", "stato"])
                w.writerow([10, "Imp", "attivo"])
                w.writerow(["", "", "attivo"])
            n, sk = app._import_csv_file(str(path))
            assert (n, sk) == (1, 1)
            app.action_archive_done()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "ConfirmScreen"
            await pilot.click(app.screen.query_one("#yes-btn"))
            await pilot.pause()
            await pilot.pause()
            assert all(not t.done for t in app.todos)
            assert len(m.load_archive()) == 1
            await pilot.press("u")
            await pilot.pause()
            assert len(app.todos) == 2 and m.load_archive() == []

    run(t())


def test_settings_e_menu(tmp_files):
    async def t():
        app = make_app([make_todo("A")])
        async with app.run_test(size=(140, 50)) as pilot:
            await pilot.pause()
            from src.main import CarpeDiemMenuProvider, SettingsScreen

            names = [t for t, _, _ in CarpeDiemMenuProvider.MENU_IT]
            assert "Impostazioni" in names and "Backup: crea ora" in names
            app.action_open_settings()
            await pilot.pause()
            await pilot.pause()
            assert isinstance(app.screen, SettingsScreen)
            app.screen.query_one("#set-daily", Input).value = "7"
            await pilot.press("ctrl+enter")
            await pilot.pause()
            await pilot.pause()
            assert app.config["daily_goal"] == 7
            app.action_backup_now()
            await pilot.pause()
            assert len(m.list_snapshots()) >= 1  # +1, oltre l'eventuale auto-backup
            app.action_restore_backup()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "RestoreScreen"
            await pilot.press("escape")
            await pilot.pause()

    run(t())
