"""Slot temporali in Buongiorno (Fase 6.5: UI passiva sullo scheduler)."""

import asyncio
from datetime import datetime, timedelta

from textual.widgets import Input

from src.lang import T as _T
from src.models import Priority
from src.planner import Planner
from src.planner.models import TimeWindow
from src.screens.plan import PlanProposalScreen
from tests.conftest import make_app, make_todo, screen_texts


def _day(offset: int) -> str:
    return (datetime.now().date() + timedelta(days=offset)).strftime("%Y-%m-%d")


def _todos():
    return [
        make_todo("A-ritardo", todo_id=1, due=_day(-1), priority=Priority.HIGH),
        make_todo("B-oggi", todo_id=2, due=_day(0), stima_pomo=2),
        make_todo("C-libero", todo_id=3, priority=Priority.LOW),
    ]


def test_vuoto_nessuno_slot(tmp_files):
    async def t():
        app = make_app(_todos())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("P")
            await pilot.pause()
            await pilot.pause()
            txt = screen_texts(app.screen)
            assert _T("planp_slots_none") in txt
            assert "–" not in txt  # nessuno slot senza ora di inizio

    asyncio.run(t())


def test_slot_con_ordine_e_titoli(tmp_files):
    async def t():
        app = make_app(_todos())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("P")
            await pilot.pause()
            await pilot.pause()
            screen = app.screen
            screen.query_one("#planp-start", Input).value = "09:00"
            await pilot.pause()
            await pilot.pause()
            txt = screen_texts(screen)
            assert "09:00–09:30 A-ritardo" in txt
            assert "09:30–10:30 B-oggi" in txt
            assert "10:30–11:00 C-libero" in txt
            # Stesse righe dello scheduler diretto: la UI non ricalcola nulla.
            sched = Planner.schedule(
                screen.plan,
                [
                    TimeWindow(
                        datetime.fromisoformat(f"{_day(0)} 09:00"),
                        datetime.fromisoformat(f"{_day(0)} 15:00"),
                    )
                ],
            )
            assert [s.item.todo_id for s in sched.scheduled] == [1, 2, 3]

    asyncio.run(t())


def test_ora_invalida_senza_crash(tmp_files):
    async def t():
        app = make_app(_todos())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("P")
            await pilot.pause()
            await pilot.pause()
            screen = app.screen
            screen.query_one("#planp-start", Input).value = "xx"
            await pilot.pause()
            await pilot.pause()
            assert _T("planp_start_bad") in screen_texts(screen)

    asyncio.run(t())


def test_non_schedulati_in_sezione(tmp_files):
    async def t():
        app = make_app(_todos())
        app.config["day_hours"] = 1.0  # finestra 1h: entra solo A+B
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("P")
            await pilot.pause()
            await pilot.pause()
            screen = app.screen
            screen.query_one("#planp-start", Input).value = "09:00"
            await pilot.pause()
            await pilot.pause()
            txt = screen_texts(screen)
            assert "09:00–09:30 A-ritardo" in txt
            assert _T("planp_slots_un", t="B-oggi") in txt
            assert "09:30–10:30 B-oggi" not in txt

    asyncio.run(t())


def test_midnight_clippato_dallo_scheduler(tmp_files):
    # Nessuna logica speciale in UI: vale il comportamento dello scheduler
    # (clip al giorno, resto unscheduled).
    async def t():
        app = make_app(_todos())
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            screen = PlanProposalScreen(
                app.todos, lambda: None, today="2026-09-10", hours=6.0
            )
            await app.push_screen(screen)
            await pilot.pause()
            screen.query_one("#planp-start", Input).value = "23:00"
            await pilot.pause()
            await pilot.pause()
            txt = screen_texts(screen)
            assert "23:00–23:30 A-ritardo" in txt
            assert "B-oggi" in txt  # 1h oltre mezzanotte: non collocabile

    asyncio.run(t())


def test_conferma_invaiata_con_slot(tmp_files):
    async def t():
        app = make_app(_todos())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("P")
            await pilot.pause()
            await pilot.pause()
            app.screen.query_one("#planp-start", Input).value = "09:00"
            await pilot.pause()
            await pilot.pause()
            await pilot.press("ctrl+enter")
            await pilot.pause()
            await pilot.pause()
            by_id = {t.id: t for t in app.todos}
            assert by_id[1].planned_for == _day(0)
            assert by_id[2].planned_for == _day(0)
            assert by_id[3].planned_for == _day(0)

    asyncio.run(t())
