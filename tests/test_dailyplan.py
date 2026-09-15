"""Piano giorno navigabile: evidenziazione, dispatch, click, layout (isolati)."""

import asyncio
from datetime import datetime, timedelta

from textual.widgets import ListView

from tests.conftest import make_app, make_todo


def _day(offset: int) -> str:
    return (datetime.now().date() + timedelta(days=offset)).strftime("%Y-%m-%d")


def _todos():
    return [
        make_todo("P1", todo_id=1, planned_for=_day(0)),
        make_todo("P2", todo_id=2, planned_for=_day(0)),
        make_todo("D1", todo_id=3, due=_day(0)),
        make_todo("D2", todo_id=4, due=_day(0)),
        make_todo("O1", todo_id=5, due=_day(-2)),
        make_todo("U1", todo_id=6),
    ]


def _cur(screen):
    item = screen.query_one("#plan-section", ListView).highlighted_child
    return getattr(item, "task_id", None), getattr(item, "section", None)


def test_aggiungi_secondo_non_primo(tmp_files):
    async def t():
        app = make_app(_todos())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_view_daily_plan()
            await pilot.pause()
            await pilot.pause()
            assert _cur(app.screen) == (1, "planned")
            await pilot.press("down")  # P2
            await pilot.pause()
            await pilot.press("down")  # salta header, D1
            await pilot.pause()
            await pilot.press("down")  # D2
            await pilot.pause()
            assert _cur(app.screen) == (4, "due")
            await pilot.press("+")
            await pilot.pause()
            await pilot.pause()
            by_id = {x.id: x for x in app.todos}
            assert by_id[4].planned_for == _day(0)
            assert by_id[3].planned_for == ""  # il primo NON toccato
            assert _cur(app.screen)[0] == 4  # highlight resta su D2

    asyncio.run(t())


def test_rimuovi_e_sospendi_secondo(tmp_files):
    async def t():
        app = make_app(_todos())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_view_daily_plan()
            await pilot.pause()
            await pilot.pause()
            await pilot.press("down")  # P2
            await pilot.pause()
            await pilot.press("x")
            await pilot.pause()
            await pilot.pause()
            by_id = {x.id: x for x in app.todos}
            assert by_id[2].planned_for == ""
            assert by_id[1].planned_for == _day(0)
            await pilot.press("escape")  # riapri: highlight su P1
            await pilot.pause()
            app.action_view_daily_plan()
            await pilot.pause()
            await pilot.pause()
            assert _cur(app.screen) == (1, "planned")
            await pilot.press("space")  # scelta stato come in home
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "StateChoiceScreen"
            await pilot.press("right")  # Attivo -> Sospeso
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            by_id = {x.id: x for x in app.todos}
            assert by_id[1].paused is True

    asyncio.run(t())


def test_noop_su_sezione_sbagliata(tmp_files):
    async def t():
        app = make_app(_todos())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_view_daily_plan()
            await pilot.pause()
            await pilot.pause()
            assert _cur(app.screen) == (1, "planned")
            await pilot.press("+")  # + su pianificato: niente
            await pilot.pause()
            by_id = {x.id: x for x in app.todos}
            assert by_id[1].planned_for == _day(0)
            assert all(x.planned_for != _day(0) or x.id in (1, 2) for x in app.todos)

    asyncio.run(t())


def test_click_sposta_evidenziazione(tmp_files):
    async def t():
        app = make_app(_todos())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_view_daily_plan()
            await pilot.pause()
            await pilot.pause()
            lv = app.screen.query_one("#plan-section", ListView)
            rows = [c for c in lv.children if getattr(c, "task_id", None) is not None]
            await pilot.click(rows[3])  # D2
            await pilot.pause()
            assert _cur(app.screen) == (4, "due")

    asyncio.run(t())


def test_layout_basso(tmp_files):
    async def t():
        todos = [
            make_todo(f"T{i}", todo_id=i, planned_for=_day(0)) for i in range(1, 20)
        ]
        app = make_app(todos)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            app.action_view_daily_plan()
            await pilot.pause()
            await pilot.pause()
            box = app.screen.query_one("#plan-box").region
            btn = app.screen.query_one("#plan-close").region
            assert box.y + box.height <= 24, box
            assert btn.y + btn.height <= 24, btn
            assert btn.y >= box.y and btn.y + btn.height <= box.y + box.height

    asyncio.run(t())


def test_week_layout_terminale_piccolo(tmp_files):
    """La cornice settimana contiene lista + Chiudi a terminale piccolo."""

    async def t():
        todos = [make_todo(f"T{i}", todo_id=i, due=_day(i % 7)) for i in range(1, 20)]
        for size in ((120, 40), (80, 24)):
            app = make_app(todos)
            async with app.run_test(size=size) as pilot:
                await pilot.pause()
                app.action_view_week()
                await pilot.pause()
                await pilot.pause()
                assert type(app.screen).__name__ == "WeekScreen"
                box = app.screen.query_one("#week-box").region
                btn = app.screen.query_one("#week-close").region
                lst = app.screen.query_one("#week-list").region
                for name, reg in (("close", btn), ("list", lst)):
                    assert reg.y >= box.y, (size, name, reg, box)
                    assert reg.y + reg.height <= box.y + box.height, (
                        size,
                        name,
                        reg,
                        box,
                    )

    asyncio.run(t())


def test_prossimi_visibili_e_aggiungibili(tmp_files):
    """Task con scadenza futura visibili in p e aggiungibili con +."""

    async def t():
        todos = [
            make_todo("Futura", todo_id=1, due=_day(2)),
            make_todo("Ritardo", todo_id=2, due=_day(-2)),
        ]
        app = make_app(todos)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_view_daily_plan()
            await pilot.pause()
            await pilot.pause()
            lv = app.screen.query_one("#plan-section", ListView)
            rows = [
                (getattr(c, "task_id", None), getattr(c, "section", None))
                for c in lv.children
            ]
            assert (1, "upcoming") in rows
            assert (2, "overdue") in rows
            for _ in range(10):
                cur = lv.highlighted_child
                if getattr(cur, "task_id", None) == 1:
                    break
                await pilot.press("down")
                await pilot.pause()
            assert _cur(app.screen) == (1, "upcoming")
            await pilot.press("+")
            await pilot.pause()
            await pilot.pause()
            by_id = {x.id: x for x in app.todos}
            assert by_id[1].planned_for == _day(0)
            lv2 = app.screen.query_one("#plan-section", ListView)
            rows2 = [
                (getattr(c, "task_id", None), getattr(c, "section", None))
                for c in lv2.children
            ]
            assert (1, "planned") in rows2
            assert (1, "upcoming") not in rows2

    asyncio.run(t())


def test_scaduto_pianificato_senza_duplicato(tmp_files):
    """Dopo + lo scaduto sta solo in Pianificati, non anche in Ritardo."""

    async def t():
        app = make_app([make_todo("Ritardo", todo_id=1, due=_day(-2))])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_view_daily_plan()
            await pilot.pause()
            await pilot.pause()
            assert _cur(app.screen) == (1, "overdue")
            await pilot.press("+")
            await pilot.pause()
            await pilot.pause()
            by_id = {x.id: x for x in app.todos}
            assert by_id[1].planned_for == _day(0)
            lv = app.screen.query_one("#plan-section", ListView)
            rows = [
                (getattr(c, "task_id", None), getattr(c, "section", None))
                for c in lv.children
            ]
            assert (1, "planned") in rows
            assert (1, "overdue") not in rows

    asyncio.run(t())
