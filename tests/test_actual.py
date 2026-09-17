"""Tempo effettivo: ActualScreen nel flusso, calibrazione nel piano (isolati)."""

from textual.widgets import Button, Input

import src.domain as domain
from tests.conftest import make_app, make_todo, run, screen_texts, wait_for


def test_actual_chiesto_e_salvato(tmp_files):
    async def t():
        app = make_app([make_todo("Stimato", todo_id=1, stima_pomo=3, pomodoros=2)])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "StateChoiceScreen"
            await pilot.press("down")
            await pilot.pause()
            assert getattr(app.screen.focused, "id", None) == "completato-btn"
            await pilot.press("enter")
            ok = await wait_for(
                pilot, lambda: type(app.screen).__name__ == "ActualScreen"
            )
            assert ok
            # default = pomodori contati
            assert app.screen.query_one("#actual-input", Input).value == "2"
            await pilot.click("#actual-save")
            ok = await wait_for(pilot, lambda: app.todos[0].actual_pomo == 2)
            assert ok
            assert app.todos[0].done is True

    run(t())


def test_actual_saltato_con_esc(tmp_files):
    async def t():
        app = make_app([make_todo("Stimato", todo_id=1, stima_pomo=3)])
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
            await pilot.pause()
            await pilot.pause()
            assert app.todos[0].done is True
            assert app.todos[0].actual_pomo == 0

    run(t())


def test_nessun_actual_senza_stima(tmp_files):
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
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ != "ActualScreen"
            assert app.todos[0].done is True

    run(t())


def test_actual_valore_custom_e_scarto(tmp_files):
    async def t():
        app = make_app([make_todo("Stimato", todo_id=1, stima_pomo=2)])
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
            app.screen.query_one("#actual-input", Input).value = "5"
            await pilot.pause()
            import src.lang as lang_module

            assert "+3" in screen_texts(app.screen) or "+3" in str(
                app.screen.query_one("#actual-diff").renderable
            )
            assert lang_module.T("actual_invalid") not in screen_texts(app.screen)
            await pilot.click("#actual-save")
            ok = await wait_for(pilot, lambda: app.todos[0].actual_pomo == 5)
            assert ok
            # valore invalido: resta aperta
            app2done = app.todos[0]
            assert app2done.done is True

    run(t())


def test_actual_invalido_resta_aperta(tmp_files):
    async def t():
        app = make_app([make_todo("Stimato", todo_id=1, stima_pomo=2)])
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
            app.screen.query_one("#actual-input", Input).value = "cento"
            await pilot.pause()
            await pilot.click("#actual-save")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "ActualScreen"
            assert app.todos[0].actual_pomo == 0

    run(t())


def _seed_calibrazione():
    done = []
    for i in range(1, 6):
        t = make_todo(f"Fatto{i}", todo_id=i, stima_pomo=2)
        t.done = True
        t.completed_at = "2026-09-12 10:00"
        t.actual_pomo = 4
        done.append(t)
    done.append(make_todo("Attivo", todo_id=9, stima_pomo=2))
    return done


def test_buongiorno_mostra_calibrata(tmp_files):
    async def t():
        assert domain.calibration_factor(_seed_calibrazione()) == 2.0
        app = make_app(_seed_calibrazione())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_plan_day()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "PlanProposalScreen"
            from textual.widgets import SelectionList

            import src.lang as lang_module

            labels = " ".join(
                str(o.prompt)
                for o in app.screen.query_one("#planp-list", SelectionList)._options
            )
            assert lang_module.T("plan_calibrated", f="x2.0") in labels

    run(t())


def test_detail_e_stats_mostrano_actual(tmp_files):
    async def t():
        app = make_app(_seed_calibrazione())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            import src.lang as lang_module

            app.action_view_stats()
            await pilot.pause()
            await pilot.pause()
            assert "x2.0" in screen_texts(app.screen)
            await pilot.press("escape")
            await pilot.pause()
            # dettaglio del completato con actual
            app.filter_state = "completati"
            app._populate_table()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "DetailScreen"
            assert lang_module.T("detail_actual", n=4) in screen_texts(app.screen)

    run(t())


def test_actual_dal_piano_giorno(tmp_files):
    async def t():
        app = make_app([make_todo("Stimato", todo_id=1, stima_pomo=2)])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_view_daily_plan()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "DailyPlanScreen"
            await pilot.press("space")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "StateChoiceScreen"
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("enter")
            ok = await wait_for(
                pilot, lambda: type(app.screen).__name__ == "ActualScreen"
            )
            assert ok
            await pilot.click("#actual-save")
            ok = await wait_for(pilot, lambda: app.todos[0].actual_pomo == 2)
            assert ok

    run(t())


def test_actual_layout_terminale_piccolo(tmp_files):
    async def t():
        for size in ((120, 40), (80, 24), (70, 20)):
            app = make_app([make_todo("Stimato", todo_id=1, stima_pomo=2)])
            async with app.run_test(size=size) as pilot:
                await pilot.pause()
                app._apply_state(app.todos[0], "completato")
                ok = await wait_for(
                    pilot, lambda: type(app.screen).__name__ == "ActualScreen"
                )
                assert ok, size
                box = app.screen.query_one("#actual-box").region
                for wid in ("#actual-save", "#actual-skip"):
                    reg = app.screen.query_one(wid, Button).region
                    assert reg.y >= box.y, (size, wid, reg, box)
                    assert reg.y + reg.height <= box.y + box.height, (
                        size,
                        wid,
                        reg,
                        box,
                    )
                await pilot.press("escape")
                await pilot.pause()

    run(t())
