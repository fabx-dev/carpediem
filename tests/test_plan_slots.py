"""Disponibilita' start/end espliciti e slot in Buongiorno (UI passiva)."""

import asyncio
from datetime import datetime, timedelta

from textual.widgets import Input, TextArea

from src.lang import T as _T
from src.models import Priority
from src.planner import Planner
from src.planner.models import TimeWindow
from tests.conftest import make_app, make_todo, screen_texts


def _day(offset: int) -> str:
    return (datetime.now().date() + timedelta(days=offset)).strftime("%Y-%m-%d")


def _todos():
    return [
        make_todo("A-ritardo", todo_id=1, due=_day(-1), priority=Priority.HIGH),
        make_todo("B-oggi", todo_id=2, due=_day(0), stima_pomo=2),
        make_todo("C-libero", todo_id=3, priority=Priority.LOW),
    ]


async def _set_times(pilot, screen, start=None, end=None):
    if start is not None:
        screen.query_one("#planp-start", Input).value = start
    if end is not None:
        screen.query_one("#planp-end", Input).value = end
    await pilot.pause()
    await pilot.pause()


async def _set_events(pilot, screen, text):
    area = screen.query_one("#planp-events", TextArea)
    area.text = text
    area.post_message(TextArea.Changed(area))
    await pilot.pause()
    await pilot.pause()


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
            assert "–" not in txt  # nessuno slot senza finestra

    asyncio.run(t())


def test_start_senza_end_hint(tmp_files):
    async def t():
        app = make_app(_todos())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("P")
            await pilot.pause()
            await pilot.pause()
            await _set_times(pilot, app.screen, start="09:00")
            txt = screen_texts(app.screen)
            assert _T("planp_end_missing") in txt
            assert "09:00–" not in txt  # nessuno slot senza fine

    asyncio.run(t())


def test_end_senza_start_hint_base(tmp_files):
    async def t():
        app = make_app(_todos())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("P")
            await pilot.pause()
            await pilot.pause()
            await _set_times(pilot, app.screen, end="18:00")
            # Senza inizio non c'e' finestra: hint base, mai scheduling.
            assert _T("planp_slots_none") in screen_texts(app.screen)

    asyncio.run(t())


def test_end_uguale_o_minore_di_start(tmp_files):
    async def t():
        for start, end in (("09:00", "09:00"), ("09:00", "08:30"), ("23:00", "02:00")):
            app = make_app(_todos())
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await pilot.press("P")
                await pilot.pause()
                await pilot.pause()
                await _set_times(pilot, app.screen, start=start, end=end)
                txt = screen_texts(app.screen)
                assert _T("planp_window_bad") in txt, (start, end)
                assert "09:00–09:30" not in txt

    asyncio.run(t())


def test_ora_invalida_senza_crash(tmp_files):
    async def t():
        app = make_app(_todos())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("P")
            await pilot.pause()
            await pilot.pause()
            await _set_times(pilot, app.screen, start="xx", end="18:00")
            assert _T("planp_start_bad") in screen_texts(app.screen)

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
            await _set_times(pilot, screen, start="09:00", end="18:00")
            txt = screen_texts(screen)
            assert "09:00–09:30 A-ritardo" in txt
            assert "09:30–10:30 B-oggi" in txt
            assert "10:30–11:00 C-libero" in txt
            # Stesse righe dello scheduler diretto con la STESSA finestra
            # esplicita: la UI non ricalcola nulla e day_hours non c'entra.
            sched = Planner.schedule(
                screen.plan,
                [
                    TimeWindow(
                        datetime.fromisoformat(f"{_day(0)} 09:00"),
                        datetime.fromisoformat(f"{_day(0)} 18:00"),
                    )
                ],
            )
            assert [s.item.todo_id for s in sched.scheduled] == [1, 2, 3]

    asyncio.run(t())


def test_finestra_corta_e_unscheduled(tmp_files):
    async def t():
        app = make_app(_todos())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("P")
            await pilot.pause()
            await pilot.pause()
            screen = app.screen
            # Finestra 1h reale: A (30m) entra, B (1h) no -> senza orario.
            await _set_times(pilot, screen, start="09:00", end="10:00")
            txt = screen_texts(screen)
            assert "09:00–09:30 A-ritardo" in txt
            assert _T("planp_slots_un", t="B-oggi") in txt
            assert "09:30–10:30 B-oggi" not in txt

    asyncio.run(t())


def test_conferma_invaiata_con_slot(tmp_files):
    async def t():
        app = make_app(_todos())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("P")
            await pilot.pause()
            await pilot.pause()
            await _set_times(pilot, app.screen, start="09:00", end="18:00")
            await pilot.press("ctrl+enter")
            await pilot.pause()
            await pilot.pause()
            by_id = {t.id: t for t in app.todos}
            assert by_id[1].planned_for == _day(0)
            assert by_id[2].planned_for == _day(0)
            assert by_id[3].planned_for == _day(0)

    asyncio.run(t())


def test_evento_in_timeline_e_slot_spostati(tmp_files):
    async def t():
        app = make_app(_todos())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("P")
            await pilot.pause()
            await pilot.pause()
            screen = app.screen
            await _set_times(pilot, screen, start="09:00", end="18:00")
            await _set_events(pilot, screen, "10:00-11:00 Riunione")
            txt = screen_texts(screen)
            assert "09:00–09:30 A-ritardo" in txt
            assert "10:00–11:00 EVENTO: Riunione" in txt
            # B da 1h non entra piu' prima dell'evento (va dopo);
            # C da 30min entra in 09:30-10:00 (first-fit nell'ordine Planner).
            assert "11:00–12:00 B-oggi" in txt
            assert "09:30–10:00 C-libero" in txt

    asyncio.run(t())


def test_evento_pausa_pranzo_nessun_overlap(tmp_files):
    async def t():
        # Finestra 09:00-18:00 con evento 13:00-14:00: nessuno slot tocca
        # l'evento e nessuno esce dalla finestra (algoritmo invariato).
        app = make_app(_todos())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("P")
            await pilot.pause()
            await pilot.pause()
            screen = app.screen
            await _set_times(pilot, screen, start="09:00", end="18:00")
            await _set_events(pilot, screen, "13:00-14:00 Pausa pranzo")
            txt = screen_texts(screen)
            assert "13:00–14:00 EVENTO: Pausa pranzo" in txt
            lo = datetime.fromisoformat(f"{_day(0)} 09:00")
            busy_s = datetime.fromisoformat(f"{_day(0)} 13:00")
            busy_e = datetime.fromisoformat(f"{_day(0)} 14:00")
            hi = datetime.fromisoformat(f"{_day(0)} 18:00")
            for s in screen.sched.scheduled:
                assert s.start >= lo and s.end <= hi
                assert s.end <= busy_s or s.start >= busy_e

    asyncio.run(t())


def test_evento_fuori_finestra_non_mostrato(tmp_files):
    async def t():
        app = make_app(_todos())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("P")
            await pilot.pause()
            await pilot.pause()
            screen = app.screen
            await _set_times(pilot, screen, start="09:00", end="18:00")
            await _set_events(pilot, screen, "20:00-21:00 Sera")
            txt = screen_texts(screen)
            assert "Sera" not in txt  # fuori [09:00, 18:00): non renderizzato
            assert "09:00–09:30 A-ritardo" in txt  # scheduling invariato

    asyncio.run(t())


def test_riga_evento_invalida_segnalata(tmp_files):
    async def t():
        app = make_app(_todos())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("P")
            await pilot.pause()
            await pilot.pause()
            screen = app.screen
            await _set_times(pilot, screen, start="09:00", end="18:00")
            await _set_events(pilot, screen, "10:00-11:00 Ok\nxx")
            txt = screen_texts(screen)
            assert "10:00–11:00 EVENTO: Ok" in txt  # valida applicata
            assert "xx" in txt  # invalida segnalata, senza crash

    asyncio.run(t())
