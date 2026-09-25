"""Gate Enter nel Piano: Detail solo per righe effettivamente pianificate.

Le sezioni due/overdue/upcoming/unplanned non sono in piano oggi: aprirne
il Detail mostrerebbe un Why ricalcolato ("Pianificato oggi") incoerente
con lo stato reale. Home e altre schermate restano invariate.
"""

from datetime import datetime, timedelta

from textual.widgets import ListView

from src import domain
from src.lang import T
from tests.conftest import make_app, make_todo, run, screen_texts


def _day(offset: int) -> str:
    return (datetime.now().date() + timedelta(days=offset)).strftime("%Y-%m-%d")


def _cur(screen):
    item = screen.query_one("#plan-section", ListView).highlighted_child
    return getattr(item, "task_id", None), getattr(item, "section", None)


async def _open_plan(pilot, app):
    app.action_view_daily_plan()
    await pilot.pause()
    await pilot.pause()
    assert type(app.screen).__name__ == "DailyPlanScreen"


async def _goto(pilot, app, tid, section):
    for _ in range(30):
        if _cur(app.screen) == (tid, section):
            return
        await pilot.press("down")
        await pilot.pause()
    raise AssertionError(f"riga {(tid, section)} non raggiunta")


def _stack_names(app):
    return [type(s).__name__ for s in app.screen_stack]


def test_enter_su_pianificato_apre_detail_con_why_e_cockpit(tmp_files):
    async def t():
        app = make_app(
            [
                make_todo(
                    "P1",
                    todo_id=1,
                    planned_for=_day(0),
                    due=_day(0),
                    stima_pomo=2,
                )
            ]
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            assert _cur(app.screen) == (1, "planned")
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "DetailScreen"
            txt = screen_texts(app.screen)
            assert T("why_title") in txt
            assert T("why_scheduled") in txt
            factor = domain.calibration_factor(app.todos)
            cd = domain.predicted_minutes(60, factor)
            assert T("cockpit_ear_row", tu="60m", cd=f"{cd}m", re="—") in txt

    run(t())


def test_enter_su_due_non_apre_detail(tmp_files):
    async def t():
        app = make_app(
            [
                make_todo("P1", todo_id=1, planned_for=_day(0)),
                make_todo("D1", todo_id=2, due=_day(0)),
            ]
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            await _goto(pilot, app, 2, "due")
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "DailyPlanScreen"
            assert "DetailScreen" not in _stack_names(app)

    run(t())


def test_enter_su_skipped_non_apre_detail(tmp_files):
    async def t():
        app = make_app(
            [
                make_todo("S1", todo_id=1, due=_day(0), plan_skip=_day(0)),
                make_todo("P1", todo_id=2, planned_for=_day(0)),
            ]
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            await _goto(pilot, app, 1, "due")
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "DailyPlanScreen"
            assert "DetailScreen" not in _stack_names(app)

    run(t())


def test_enter_su_overdue_non_apre_detail(tmp_files):
    async def t():
        app = make_app(
            [
                make_todo("O1", todo_id=1, due=_day(-2)),
                make_todo("P1", todo_id=2, planned_for=_day(0)),
            ]
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            await _goto(pilot, app, 1, "overdue")
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "DailyPlanScreen"
            assert "DetailScreen" not in _stack_names(app)

    run(t())


def test_home_enter_apre_detail_come_prima(tmp_files):
    async def t():
        app = make_app([make_todo("H1", todo_id=1, due=_day(0))])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_view_detail()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "DetailScreen"

    run(t())
