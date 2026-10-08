"""Layout StatsScreen: box e bottone sempre dentro il visibile (file isolati)."""

import asyncio

from carpediem.screens import StatsScreen
from tests.conftest import make_app, make_todo


def _many_todos():
    return [
        make_todo(
            f"T{i}",
            todo_id=i,
            done=True,
            completed_at=f"2026-09-{(i % 9) + 1:02d} 10:00",
        )
        for i in range(1, 25)
    ]


def _check_size(w, h):
    async def t():
        app = make_app(_many_todos())
        async with app.run_test(size=(w, h)) as pilot:
            await pilot.pause()
            await pilot.pause()
            app.push_screen(StatsScreen(app.todos))
            await pilot.pause()
            await pilot.pause()
            box = app.screen.query_one("#stats-box").region
            btn = app.screen.query_one("#stats-close").region
            assert box.y + box.height <= h, (w, h, box)
            assert btn.y + btn.height <= h, (w, h, btn)
            assert btn.y >= box.y
            assert btn.y + btn.height <= box.y + box.height, (w, h, box, btn)

    asyncio.run(t())


def test_stats_layout_basso(tmp_files):
    _check_size(80, 24)


def test_stats_layout_alto(tmp_files):
    _check_size(120, 40)
