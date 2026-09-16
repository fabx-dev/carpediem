"""Layout a terminale piccolo: Chiudi sempre dentro la cornice (70x20, 80x24)."""

import asyncio
from datetime import datetime
from pathlib import Path

from tests.conftest import make_app, make_todo

SIZES = ((120, 40), (80, 24), (70, 20))


def _assert_close_in_box(app, size, box_id, close_id, extra_ids=()):
    box = app.screen.query_one(f"#{box_id}").region
    regs = [("close", app.screen.query_one(f"#{close_id}").region)]
    regs += [(eid, app.screen.query_one(f"#{eid}").region) for eid in extra_ids]
    for name, reg in regs:
        assert reg.y >= box.y, (size, name, reg, box)
        assert reg.y + reg.height <= box.y + box.height, (size, name, reg, box)


def test_archive_layout_terminale_piccolo(tmp_files):
    async def t():
        archived = [
            make_todo(f"Vecchio {i}", todo_id=i, completed_at="2026-09-01 10:00")
            for i in range(1, 31)
        ]
        for size in SIZES:
            app = make_app([])
            async with app.run_test(size=size) as pilot:
                await pilot.pause()
                app.store.replace_all(archived)
                app.action_view_archive()
                await pilot.pause()
                await pilot.pause()
                assert type(app.screen).__name__ == "ArchiveScreen"
                _assert_close_in_box(app, size, "arc-box", "arc-close", ("arc-list",))

    asyncio.run(t())


def test_keys_layout_terminale_piccolo(tmp_files):
    async def t():
        for size in SIZES:
            app = make_app([])
            async with app.run_test(size=size) as pilot:
                await pilot.pause()
                app.action_show_keys()
                await pilot.pause()
                await pilot.pause()
                assert type(app.screen).__name__ == "KeysScreen"
                _assert_close_in_box(
                    app, size, "keys-box", "keys-close", ("keys-list",)
                )

    asyncio.run(t())


def test_kanban_layout_terminale_piccolo(tmp_files):
    async def t():
        todos = [make_todo(f"T{i}", todo_id=i) for i in range(1, 31)]
        for size in SIZES:
            app = make_app(todos)
            async with app.run_test(size=size) as pilot:
                await pilot.pause()
                app.action_view_kanban()
                await pilot.pause()
                await pilot.pause()
                assert type(app.screen).__name__ == "KanbanScreen"
                _assert_close_in_box(app, size, "kb-box", "kb-close", ("kb-cols",))

    asyncio.run(t())


def test_detail_layout_terminale_piccolo(tmp_files):
    async def t():
        sub = [
            make_todo(f"Figlio {i}", todo_id=100 + i, parent_id=1) for i in range(20)
        ]
        parent = make_todo("Padre", todo_id=1, notes="riga\n" * 40)
        for size in SIZES:
            app = make_app([parent] + sub)
            async with app.run_test(size=size) as pilot:
                await pilot.pause()
                app.action_view_detail()
                await pilot.pause()
                await pilot.pause()
                assert type(app.screen).__name__ == "DetailScreen"
                _assert_close_in_box(
                    app, size, "detail-box", "detail-close", ("detail-scroll",)
                )

    asyncio.run(t())


def test_calendar_layout_terminale_piccolo(tmp_files):
    async def t():
        today = datetime.now()
        todos = [
            make_todo(f"T{i}", todo_id=i, due=today.strftime("%Y-%m-%d"))
            for i in range(1, 11)
        ]
        for size in SIZES:
            app = make_app(todos)
            async with app.run_test(size=size) as pilot:
                await pilot.pause()
                app.action_view_calendar()
                await pilot.pause()
                await pilot.pause()
                assert type(app.screen).__name__ == "CalendarScreen"
                _assert_close_in_box(
                    app, size, "calendar-box", "calendar-close", ("calendar-scroll",)
                )

    asyncio.run(t())


def test_welcome_body_non_sborda(tmp_files):
    """Il testo del popup iniziale resta dentro la cornice (it + en)."""
    import src.lang as lang
    from src.screens.system import WelcomeScreen

    async def t():
        for language in ("it", "en"):
            lang.set_lang(language)
            try:
                for size in SIZES:
                    app = make_app([])
                    async with app.run_test(size=size) as pilot:
                        await pilot.pause()
                        app.push_screen(WelcomeScreen())
                        await pilot.pause()
                        await pilot.pause()
                        assert type(app.screen).__name__ == "WelcomeScreen"
                        box = app.screen.query_one("#wel-box").region
                        body = app.screen.query_one("#wel-body").region
                        assert body.x >= box.x, (language, size, body, box)
                        assert body.x + body.width <= box.x + box.width, (
                            language,
                            size,
                            body,
                            box,
                        )
            finally:
                lang.set_lang("it")

    asyncio.run(t())


def test_template_layout_terminale_piccolo(tmp_files):
    async def t():
        for size in SIZES:
            app = make_app([])
            app.templates = {f"Tpl {i}": [{"title": "x"}] for i in range(20)}
            async with app.run_test(size=size) as pilot:
                await pilot.pause()
                app._open_template_picker()
                await pilot.pause()
                await pilot.pause()
                assert type(app.screen).__name__ == "TemplateScreen"
                _assert_close_in_box(app, size, "tpl-box", "tpl-close", ("tpl-list",))

    asyncio.run(t())


def test_day_layout_terminale_piccolo(tmp_files):
    async def t():
        today = datetime.now().date()
        todos = [
            make_todo(f"T{i}", todo_id=i, due=today.strftime("%Y-%m-%d"))
            for i in range(1, 31)
        ]
        for size in SIZES:
            app = make_app(todos)
            async with app.run_test(size=size) as pilot:
                await pilot.pause()
                app.action_open_day(today.year, today.month, today.day)
                await pilot.pause()
                await pilot.pause()
                assert type(app.screen).__name__ == "DayScreen"
                _assert_close_in_box(app, size, "day-box", "day-close", ("day-list",))

    asyncio.run(t())


def test_theme_templateproject_impcsv_restore_layout_piccolo(tmp_files):
    from src.screens.form import RadarPickScreen, ThemeListScreen
    from src.screens.system import RestoreScreen
    from src.screens.views import ImportCsvScreen, TemplateProjectScreen

    async def t():
        cases = [
            (
                ThemeListScreen([f"tema-{i}" for i in range(30)], "tema-0"),
                "theme-box",
                "theme-close",
                "theme-list",
            ),
            (
                RadarPickScreen([(i, f"task-{i}", -i) for i in range(1, 9)]),
                "pick-box",
                "pick-close",
                "pick-list",
            ),
            (
                TemplateProjectScreen([(f"prog-{i}", i) for i in range(20)]),
                "tplp-box",
                "tplp-close",
                "tplp-list",
            ),
            (
                ImportCsvScreen([Path(f"/tmp/f{i}.csv") for i in range(20)]),
                "impcsv-box",
                "impcsv-cancel",
                "impcsv-list",
            ),
            (
                RestoreScreen([Path(f"/tmp/s{i}.zip") for i in range(20)]),
                "rst-box",
                "rst-close",
                "rst-list",
            ),
        ]
        for size in SIZES:
            for scr, box, close, lst in cases:
                app = make_app([])
                async with app.run_test(size=size) as pilot:
                    await pilot.pause()
                    app.push_screen(scr)
                    await pilot.pause()
                    await pilot.pause()
                    _assert_close_in_box(app, size, box, close, (lst,))

    asyncio.run(t())
