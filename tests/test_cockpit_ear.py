"""Cockpit #47: Tu / CarpeDiem / Reale nel Detail, significati separati.

Tu = stima originale (mai riscritta); CarpeDiem = previsione calibrata
(fallback = stima senza storia); Reale = actual o dash.
"""

import src.screens.views as views_mod
from src.lang import T
from tests.conftest import make_app, make_todo, run, screen_texts


async def _open_detail(pilot, app, todo):
    app.push_screen(views_mod.DetailScreen(todo, app.todos))
    await pilot.pause()
    await pilot.pause()
    assert type(app.screen).__name__ == "DetailScreen"


def test_ear_tre_valori_distinti(tmp_files):
    def t():
        async def inner():
            app = make_app([make_todo("A", todo_id=1, stima_pomo=2)])
            app.todos[0].actual_pomo = 3
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await _open_detail(pilot, app, app.todos[0])
                txt = screen_texts(app.screen)
                assert T("cockpit_ear_row", tu="60m", cd="60m", re="90m") in txt
                # stima originale intatta su disco e in memoria
                assert app.todos[0].stima_pomo == 2

        return inner()

    run(t())


def test_ear_senza_storia_e_senza_actual(tmp_files):
    def t():
        async def inner():
            app = make_app([make_todo("A", todo_id=1, stima_pomo=2)])
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await _open_detail(pilot, app, app.todos[0])
                txt = screen_texts(app.screen)
                # senza storia: previsione = stima; senza actual: dash
                assert T("cockpit_ear_row", tu="60m", cd="60m", re="—") in txt

        return inner()

    run(t())


def test_ear_calibrata_con_storia(tmp_files):
    def t():
        async def inner():
            todos = []
            for i in range(1, 6):
                f = make_todo(f"F{i}", todo_id=100 + i, stima_pomo=2)
                f.done = True
                f.completed_at = "2026-09-12 10:00"
                f.actual_pomo = 3
                todos.append(f)
            todos.append(make_todo("A", todo_id=1, stima_pomo=2))
            app = make_app(todos)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await _open_detail(pilot, app, app.todos[-1])
                txt = screen_texts(app.screen)
                # factor 1.5 -> 90m; stima utente resta 2
                assert T("cockpit_ear_row", tu="60m", cd="90m", re="—") in txt
                assert app.todos[-1].stima_pomo == 2

        return inner()

    run(t())


def test_ear_niente_senza_stima(tmp_files):
    def t():
        async def inner():
            app = make_app([make_todo("A", todo_id=1)])
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await _open_detail(pilot, app, app.todos[0])
                txt = screen_texts(app.screen)
                assert "Tu:" not in txt and "You:" not in txt

        return inner()

    run(t())
