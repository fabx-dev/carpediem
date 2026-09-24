"""Why nel Detail M3: sezione da PlanningDecision, mai logica duplicata.

Decisione reale, evidence reale, motivo principale reale; non valutato ->
messaggio esplicito per stato; coerenza Planner/Detail a parita' di
(todos, today, hours); Esc e assenza dati senza crash.
"""

from datetime import datetime

import src.planner.decisions as dec
from src.lang import T
from src.planner import Planner, decide
from src.screens.views import DetailScreen
from tests.conftest import make_app, make_todo, run, screen_texts, wait_for

TODAY = "2026-09-10"


async def _open_detail(pilot, app, todo, today=TODAY, hours=6.0):
    app.push_screen(DetailScreen(todo, app.todos, today=today, hours=hours))
    await pilot.pause()
    await pilot.pause()
    assert type(app.screen).__name__ == "DetailScreen"


def test_why_scheduled_con_evidence_e_motivo(tmp_files):
    def t():
        async def inner():
            app = make_app([make_todo("A", todo_id=1, due="2026-09-01", stima_pomo=2)])
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await _open_detail(pilot, app, app.todos[0])
                txt = screen_texts(app.screen)
                assert T("why_title") in txt
                assert T("why_scheduled") in txt
                assert "2026-09-01" in txt  # evidence due reale
                assert T("plan_overdue") in txt  # motivo principale reale

        return inner()

    run(t())


def test_why_not_scheduled_con_alternativa(tmp_files):
    def t():
        async def inner():
            app = make_app([make_todo(f"T{i}", todo_id=i) for i in range(1, 8)])
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await _open_detail(pilot, app, app.todos[4], hours=1.0)
                txt = screen_texts(app.screen)
                assert T("why_not_scheduled") in txt
                assert T("plan_cut") in txt
                assert T("why_alt_cut", e=1, c="2", r=5, n=7) in txt

        return inner()

    run(t())


def test_why_deferred_con_rimando(tmp_files):
    def t():
        async def inner():
            app = make_app(
                [make_todo("S", todo_id=1, plan_skip=TODAY), make_todo("A", todo_id=2)]
            )
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await _open_detail(pilot, app, app.todos[0])
                txt = screen_texts(app.screen)
                assert T("why_deferred") in txt
                assert T("plan_skipped") in txt
                assert T("why_alt_deferred") in txt

        return inner()

    run(t())


def test_why_non_valutato_per_stato(tmp_files):
    def t():
        async def inner():
            done = make_todo("D", todo_id=1)
            done.done = True
            paused = make_todo("P", todo_id=2)
            paused.paused = True
            app = make_app([done, paused])
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await _open_detail(pilot, app, app.todos[0])
                assert T("why_no_decision_done") in screen_texts(app.screen)
                await pilot.press("escape")
                await pilot.pause()
                await _open_detail(pilot, app, app.todos[1])
                assert T("why_no_decision_paused") in screen_texts(app.screen)

        return inner()

    run(t())


def test_coerenza_planner_detail_stessi_input(tmp_files):
    # Stessi (todos, today, hours): Detail mostra la decisione del flusso
    # principale. E' il bug che hours dimenticato introdurrebbe.
    todos = [make_todo(f"T{i}", todo_id=i) for i in range(1, 8)]
    expected = {
        d.todo_id: d.decision
        for d in decide(Planner(todos, today=TODAY, hours=1.0).propose(), todos)
    }
    assert expected[5] == dec.NOT_SCHEDULED

    def t():
        async def inner():
            app = make_app(todos)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await _open_detail(pilot, app, app.todos[4], hours=1.0)
                txt = screen_texts(app.screen)
                assert T("why_not_scheduled") in txt

        return inner()

    run(t())


def test_legacy_default_senza_contesto(tmp_files):
    def t():
        async def inner():
            app = make_app([make_todo("A", todo_id=1)])
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.push_screen(DetailScreen(app.todos[0], app.todos))
                await pilot.pause()
                await pilot.pause()
                assert type(app.screen).__name__ == "DetailScreen"
                txt = screen_texts(app.screen)
                assert T("why_scheduled") in txt or T("why_no_decision") in txt

        return inner()

    run(t())


def test_esc_e_reasons_vuote_senza_crash(tmp_files):
    def t():
        async def inner():
            app = make_app([make_todo("A", todo_id=1, due="2099-01-01")])
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await _open_detail(pilot, app, app.todos[0])
                ok = await wait_for(
                    pilot, lambda: T("why_title") in screen_texts(app.screen)
                )
                assert ok
                await pilot.press("escape")
                await pilot.pause()
                assert type(app.screen).__name__ != "DetailScreen"

        return inner()

    run(t())


def test_confidence_solo_con_calibration(tmp_files):
    def t():
        async def inner():
            todos = []
            for i in range(1, 11):
                f = make_todo(f"F{i}", todo_id=100 + i, stima_pomo=2)
                f.done = True
                f.completed_at = "2026-09-12 10:00"
                f.actual_pomo = 4
                todos.append(f)
            todos.append(make_todo("A", todo_id=1, stima_pomo=2, due=TODAY))
            app = make_app(todos)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await _open_detail(pilot, app, app.todos[-1])
                txt = screen_texts(app.screen)
                # primary = primo motivo (due_today); calibrated resta in
                # reasons e accende la confidence M2 sulla durata
                assert T("plan_due_today") in txt
                assert T("why_confidence", c="MEDIUM") in txt

        return inner()

    run(t())


def test_why_oggi_reale_senza_today_esplicito(tmp_files):
    today = datetime.now().strftime("%Y-%m-%d")
    app = make_app([make_todo("A", todo_id=1, due=today)])
    plan = Planner(app.todos, today=today, hours=6.0).propose()
    assert decide(plan, app.todos)[0].decision == dec.SCHEDULED
