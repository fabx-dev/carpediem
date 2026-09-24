"""Hook M2: un TaskExecution per task completato, da ogni ingresso.

Home (popup actual e skip), piano giorno (callback on_completed), CLI done.
Dedup su (task_id, ended_at): nessuna doppia registrazione.
"""

from datetime import datetime

import src.storage as st
from src.cli import _cli_main
from src.store import TodoStore
from tests.conftest import make_app, make_todo, run, wait_for


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _window():
    return {
        "date": _today(),
        "start": "09:00",
        "end": "18:00",
        "events": [],
        "allday": [],
    }


def test_home_popup_registra_execution(tmp_files):
    async def t():
        app = make_app([make_todo("A", todo_id=1, stima_pomo=2, planned_for=_today())])
        app.config["day_window"] = _window()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            await pilot.pause()
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("enter")
            ok = await wait_for(
                pilot, lambda: type(app.screen).__name__ == "ActualScreen"
            )
            assert ok
            await pilot.click("#actual-save")
            ok = await wait_for(pilot, lambda: len(st.load_executions()) == 1)
            assert ok
            e = st.load_executions()[0]
            assert e.task_id == 1 and e.completed is True
            assert e.ended_at == app.todos[0].completed_at
            assert e.planned_minutes == 60  # slot 2 pomo da finestra
            assert e.actual_minutes == 60  # default popup = stima 2
            assert e.estimate_pomo == 2  # snapshot mai riscritto

    run(t())


def test_home_skip_popup_registra_senza_actual(tmp_files):
    async def t():
        app = make_app([make_todo("Libero", todo_id=1)])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            await pilot.pause()
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("enter")
            ok = await wait_for(pilot, lambda: len(st.load_executions()) == 1)
            assert ok
            e = st.load_executions()[0]
            assert (e.task_id, e.completed, e.actual_minutes) == (1, True, 0)
            assert e.planned_minutes == 30  # fallback or-1
            assert e.estimate_pomo == 0

    run(t())


def test_esc_popup_registra_comunque(tmp_files):
    async def t():
        app = make_app([make_todo("S", todo_id=1, stima_pomo=3)])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            await pilot.pause()
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("enter")
            ok = await wait_for(
                pilot, lambda: type(app.screen).__name__ == "ActualScreen"
            )
            assert ok
            await pilot.press("escape")
            ok = await wait_for(pilot, lambda: len(st.load_executions()) == 1)
            assert ok
            assert st.load_executions()[0].actual_minutes == 0

    run(t())


def test_piano_giorno_registra_via_callback(tmp_files):
    async def t():
        app = make_app([make_todo("P", todo_id=1, planned_for=_today())])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_view_daily_plan()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "DailyPlanScreen"
            app.screen._on_state_picked(1, "planned", "completato")
            await pilot.pause()
            ok = await wait_for(pilot, lambda: len(st.load_executions()) == 1)
            assert ok
            e = st.load_executions()[0]
            assert (e.task_id, e.completed) == (1, True)

    run(t())


def test_cli_done_registra_con_fallback(tmp_files):
    store = TodoStore([make_todo("C", todo_id=1, stima_pomo=2)])
    store.commit()
    assert _cli_main(["done", "1"]) == 0
    execs = st.load_executions()
    assert len(execs) == 1
    e = execs[0]
    assert (e.task_id, e.completed, e.planned_minutes, e.estimate_pomo) == (
        1,
        True,
        60,
        2,
    )
    # idempotente: secondo done non duplica
    assert _cli_main(["done", "1"]) == 0
    assert len(st.load_executions()) == 1
