"""#52 Progressive disclosure: L1 compatto, L2 Detail, L3 Why, L4 Stats.

L1 non contiene analytics; L2 raggiungibile da L1 con Enter; L3 (Why) e'
co-locato nel Detail; L4 (Stats/Briefing) raggiungibile dalla home.
"""

from src.lang import T
from tests.conftest import make_app, make_todo, run, screen_texts, wait_for


def test_l1_senza_analytics():
    async def t():
        app = make_app([make_todo("A", todo_id=1, stima_pomo=2)])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            home = screen_texts(app.screen)
            assert T("stats_calib").split(":")[0] not in home
            assert "CarpeDiem:" not in home

    run(t())


def test_l1_l2_l3_sequenza():
    async def t():
        app = make_app([make_todo("A", todo_id=1, stima_pomo=2, due="2099-01-01")])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            # L1 -> L2 con una interazione (Enter)
            await pilot.press("enter")
            ok = await wait_for(
                pilot, lambda: type(app.screen).__name__ == "DetailScreen"
            )
            assert ok
            # L3 (Why) co-locato nel Detail
            assert T("why_title") in screen_texts(app.screen)
            await pilot.press("escape")
            await pilot.pause()

    run(t())


def test_l4_stats_dalla_home():
    async def t():
        app = make_app([make_todo("A", todo_id=1)])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("k")
            ok = await wait_for(
                pilot, lambda: type(app.screen).__name__ == "StatsScreen"
            )
            assert ok
            await pilot.press("escape")
            await pilot.pause()

    run(t())


def test_l4_briefing_dalla_home():
    async def t():
        app = make_app([make_todo("A", todo_id=1)])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_briefing_evening()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "BriefingScreen"

    run(t())
