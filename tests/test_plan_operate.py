"""Piano giorno operativo: Enter dettaglio (+modifica), Space stato (isolati)."""

from datetime import datetime, timedelta

from textual.widgets import Input, ListView

from src.models import Recurrence
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


def test_enter_apre_dettaglio_esc_non_scrive(tmp_files):
    async def t():
        app = make_app([make_todo("P1", todo_id=1, planned_for=_day(0))])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "DetailScreen"
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "DailyPlanScreen"
            by_id = {x.id: x for x in app.todos}
            assert by_id[1].title == "P1"
            assert by_id[1].planned_for == _day(0)

    run(t())


def test_enter_dettaglio_modifica_titolo(tmp_files):
    async def t():
        app = make_app([make_todo("P1", todo_id=1, planned_for=_day(0))])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            await pilot.click(app.screen.query_one("#detail-edit"))
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "TodoFormScreen"
            app.screen.query_one("#title-input", Input).value = "P1-bis"
            await pilot.press("ctrl+enter")
            await pilot.pause()
            await pilot.pause()
            # Catena corta: form -> piano (senza riaprire il dettaglio).
            assert type(app.screen).__name__ == "DailyPlanScreen"
            by_id = {x.id: x for x in app.todos}
            assert by_id[1].title == "P1-bis"
            assert by_id[1].planned_for == _day(0)
            assert _cur(app.screen)[0] == 1  # highlight conservato

    run(t())


def test_space_completa_da_pianificati(tmp_files):
    async def t():
        app = make_app(
            [
                make_todo("P1", todo_id=1, planned_for=_day(0)),
                make_todo("P2", todo_id=2, planned_for=_day(0)),
            ]
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            assert _cur(app.screen) == (1, "planned")
            await pilot.press("space")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "StateChoiceScreen"
            await pilot.press("down")  # Attivo -> Fatto
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "DailyPlanScreen"
            by_id = {x.id: x for x in app.todos}
            assert by_id[1].done is True
            lv = app.screen.query_one("#plan-section", ListView)
            rows = [
                (getattr(c, "task_id", None), getattr(c, "section", None))
                for c in lv.children
            ]
            assert (1, "planned") not in rows
            assert (2, "planned") in rows
            # Fallback: highlight sulla prima riga rimasta della sezione.
            assert _cur(app.screen) == (2, "planned")

    run(t())


def test_space_esc_non_scrive(tmp_files):
    async def t():
        app = make_app([make_todo("P1", todo_id=1, planned_for=_day(0))])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            await pilot.press("space")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "StateChoiceScreen"
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "DailyPlanScreen"
            assert app.todos[0].state == "attivo"

    run(t())


def test_space_su_riga_non_pianificata(tmp_files):
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
            await pilot.press("space")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "StateChoiceScreen"
            await pilot.press("right")  # Attivo -> Sospeso
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            by_id = {x.id: x for x in app.todos}
            assert by_id[2].paused is True

    run(t())


def test_space_ricorrenza_crea_nuovo(tmp_files):
    async def t():
        app = make_app(
            [
                make_todo(
                    "R1",
                    todo_id=1,
                    planned_for=_day(0),
                    due=_day(0),
                    recurrence=Recurrence.DAILY,
                )
            ]
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            await pilot.press("space")
            await pilot.pause()
            await pilot.pause()
            await pilot.press("down")  # Attivo -> Fatto
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            by_id = {x.id: x for x in app.todos}
            assert by_id[1].done is True
            nuovi = [x for x in app.todos if x.id != 1]
            assert len(nuovi) == 1
            assert nuovi[0].recurrence == Recurrence.DAILY

    run(t())


def test_legend_mostra_enter_space(tmp_files):
    async def t():
        app = make_app([make_todo("P1", todo_id=1, planned_for=_day(0))])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            legend = screen_texts(app.screen)
            assert "Enter" in legend and "Space" in legend
            assert "o" in legend and "O" in legend

    run(t())


def test_pomo_avvia_da_piano(tmp_files):
    async def t():
        app = make_app([make_todo("P1", todo_id=1, planned_for=_day(0))])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            assert _cur(app.screen) == (1, "planned")
            await pilot.press("o")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "PomodoroScreen"
            assert app.focus_task_id == 1
            assert app.focus_phase == "focus"
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "DailyPlanScreen"

    run(t())


def test_pomo_riapre_popup_a_timer_attivo(tmp_files):
    async def t():
        app = make_app([make_todo("P1", todo_id=1, planned_for=_day(0))])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            await pilot.press("o")
            await pilot.pause()
            await pilot.pause()
            end1 = app.focus_end
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()
            await pilot.press("o")  # timer attivo: solo popup, no restart
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "PomodoroScreen"
            assert app.focus_task_id == 1
            assert app.focus_end == end1

    run(t())


def test_pomo_noop_piano_vuoto(tmp_files):
    async def t():
        app = make_app([])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            await pilot.press("o")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "DailyPlanScreen"
            assert app.focus_task_id is None

    run(t())


def test_pomo_pausa_da_piano(tmp_files):
    async def t():
        app = make_app([make_todo("P1", todo_id=1, planned_for=_day(0))])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            await pilot.press("O")  # nessun timer: warning, niente cambia
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "DailyPlanScreen"
            assert app.focus_task_id is None
            await pilot.press("o")
            await pilot.pause()
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()
            await pilot.press("O")
            await pilot.pause()
            assert app.focus_paused_secs is not None
            await pilot.press("O")
            await pilot.pause()
            assert app.focus_paused_secs is None

    run(t())
