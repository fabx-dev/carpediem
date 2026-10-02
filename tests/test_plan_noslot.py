"""Righe senza orario nel piano giorno: divisorio etichettato + Why distinta.

La coda senza slot e' piano confermato senza collocazione (non scarto):
il divisorio lo dichiara e il Detail lo spiega (confermato + disponibilita'
insufficiente), con la stessa story di una riga timed.
"""

from datetime import datetime, timedelta

from src.lang import T as _T
from tests.conftest import make_app, make_todo, run, screen_texts


def _day(offset: int) -> str:
    return (datetime.now().date() + timedelta(days=offset)).strftime("%Y-%m-%d")


def _todos():
    return [
        make_todo("A", todo_id=1, planned_for=_day(0)),
        make_todo("B", todo_id=2, planned_for=_day(0)),
        make_todo("C", todo_id=3, planned_for=_day(0)),
    ]


def _window(start="09:00", end="09:30"):
    return {"date": _day(0), "start": start, "end": end, "events": []}


async def _open_plan(pilot, app):
    app.action_view_daily_plan()
    await pilot.pause()
    await pilot.pause()
    assert type(app.screen).__name__ == "DailyPlanScreen"


async def _goto(pilot, screen, tid):
    for _ in range(30):
        if screen._current()[0] == tid:
            return
        await pilot.press("down")
        await pilot.pause()
    raise AssertionError(f"riga {tid} non raggiunta")


def test_divisorio_etichettato_e_coda_senza_orario(tmp_files):
    async def t():
        app = make_app(_todos())
        app.config["day_window"] = _window()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            txt = screen_texts(app.screen)
            assert _T("plan_sec_noslot") in txt  # divisorio nominato
            assert "09:00–09:30 A" in txt  # A timed
            assert "09:00–09:30 B" not in txt  # B in coda, senza prefisso

    run(t())


def test_detail_coda_senza_orario_etichetta_distinta(tmp_files):
    from tests.test_detail_why import _why_block_labels

    async def t():
        app = make_app(_todos())
        app.config["day_window"] = _window()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            await _goto(pilot, app.screen, 2)  # B in coda, senza slot
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "DetailScreen"
            txt = screen_texts(app.screen)
            assert _T("why_scheduled_noslot") in txt
            assert _T("why_scheduled") not in txt
            # Invariante story intatta anche con l'etichetta diversa
            # (B e' planned_for=oggi senza altri segnali: story fallback,
            # l'agency sta nell'etichetta + nel motivo principale).
            _why_block_labels(
                app.screen, _T("why_scheduled_noslot"), _T("why_story_sched")
            )

    run(t())


def test_detail_timed_etichetta_invariata(tmp_files):
    async def t():
        app = make_app(_todos())
        app.config["day_window"] = _window()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            await _goto(pilot, app.screen, 1)  # A timed
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            txt = screen_texts(app.screen)
            assert _T("why_scheduled") in txt
            assert _T("why_scheduled_noslot") not in txt

    run(t())
