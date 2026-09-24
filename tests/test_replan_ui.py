"""Replan Preview TUI #50: read-only fino a conferma, Esc zero scritture.

Preview = solo Planner/replan esistenti; commit solo via s (apply_replan
+ on_apply); G/menu/palette come ingressi; 3 taglie.
"""

import hashlib
from datetime import datetime

import src.storage as st
from src.lang import T
from tests.conftest import make_app, make_todo, run, screen_texts, wait_for


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _seed_window(app):
    app.config["day_window"] = {
        "date": _today(),
        "start": "09:00",
        "end": "18:00",
        "events": [],
        "allday": [],
    }


def _hashes():
    out = {}
    for p in (st.DATA_FILE, st.EXECUTIONS_FILE, st.CONFIG_FILE):
        out[str(p)] = hashlib.md5(p.read_bytes()).hexdigest() if p.exists() else None
    return out


def _app():
    return make_app(
        [
            make_todo("A", todo_id=1, planned_for=_today(), stima_pomo=2),
            make_todo("B", todo_id=2, planned_for=_today(), stima_pomo=2),
            make_todo("C", todo_id=3, stima_pomo=1),
        ]
    )


def test_preview_non_scrive(tmp_files):
    async def t():
        app = _app()
        _seed_window(app)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            before = _hashes()
            app.action_view_replan()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "ReplanPreviewScreen"
            txt = screen_texts(app.screen)
            assert T("cli_replan_moved") in txt and T("cli_replan_added") in txt
            assert _hashes() == before

    run(t())


def test_conferma_applica_conteggi(tmp_files):
    async def t():
        app = _app()
        _seed_window(app)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_view_replan()
            await pilot.pause()
            await pilot.pause()
            await pilot.press("s")
            ok = await wait_for(
                pilot, lambda: type(app.screen).__name__ != "ReplanPreviewScreen"
            )
            assert ok
            by_id = {t.id: t for t in app.todos}
            assert by_id[3].planned_for == _today()

    run(t())


def test_esc_non_scrive(tmp_files):
    async def t():
        app = _app()
        _seed_window(app)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            before = _hashes()
            app.action_view_replan()
            await pilot.pause()
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            assert type(app.screen).__name__ != "ReplanPreviewScreen"
            assert _hashes() == before
            assert app.todos[2].planned_for == ""

    run(t())


def test_tasto_g_e_tre_taglie(tmp_files):
    for size in ((120, 40), (80, 24), (70, 20)):
        _one_size(size)


def _one_size(size):
    async def t():
        app = _app()
        _seed_window(app)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await pilot.press("G")
            ok = await wait_for(
                pilot, lambda: type(app.screen).__name__ == "ReplanPreviewScreen"
            )
            assert ok, size
            txt = screen_texts(app.screen)
            assert T("rp_legend") in txt, size
            await pilot.press("escape")
            await pilot.pause()

    run(t())


def test_menu_e_palette_contengono_replan(tmp_files):
    async def t():
        app = _app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_open_menu()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "MenuScreen"
            assert T("menu_replan_t") in screen_texts(app.screen)

    run(t())
