"""Layout a terminale piccolo: Chiudi sempre dentro la cornice (70x20, 80x24)."""

import asyncio
from datetime import datetime

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
