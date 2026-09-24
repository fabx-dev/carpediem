"""Daily Cockpit #46: riga con !/durata/scadenza, leggibile a 70 colonne.

1. schedulato -> durata slot; 2. non schedulato -> stima; 3. scadenza anche
se planned; 4. alta -> !; 5. media/bassa -> niente; 6. niente wrap indesiderato.
"""

from datetime import datetime

import src.screens.plan as plan_mod
from src.models import Priority
from tests.conftest import make_app, make_todo, run, screen_texts, wait_for

_row = plan_mod.DailyPlanScreen._row


def test_riga_unit_marker_durata_scadenza():
    hi = make_todo("Urgenza", todo_id=1, priority=Priority.HIGH, due="2026-09-10")
    lo = make_todo("Routine", todo_id=2, priority=Priority.LOW)
    r_hi = _row(hi, "x", " (scad. 2026-09-10)", "09:00–09:30 ", "30m")
    r_lo = _row(lo, "+")
    assert "!" in r_hi
    assert "(30m)" in r_hi
    assert "scad. 2026-09-10" in r_hi
    assert "!" not in r_lo.replace("Routine", "")
    assert "(30m)" not in r_lo
    # stima via label pomodori esistente (nessuno slot -> stima, non minuti)
    stimato = make_todo("S", todo_id=3, stima_pomo=2)
    assert "2" in _row(stimato, "x") and "(30m)" not in _row(stimato, "x")


async def _open_plan(pilot, app):
    app.action_view_daily_plan()
    await pilot.pause()
    await pilot.pause()
    assert type(app.screen).__name__ == "DailyPlanScreen"


def test_riga_pilot_con_finestra(tmp_files):
    async def t():
        today = datetime.now().strftime("%Y-%m-%d")
        app = make_app(
            [
                make_todo(
                    "Alta con scadenza",
                    todo_id=1,
                    priority=Priority.HIGH,
                    due=today,
                    planned_for=today,
                    stima_pomo=2,
                ),
                make_todo("Media senza niente", todo_id=2, planned_for=today),
            ]
        )
        app.config["day_window"] = {
            "date": today,
            "start": "09:00",
            "end": "18:00",
            "events": [],
            "allday": [],
        }
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            ok = await wait_for(pilot, lambda: "60m" in screen_texts(app.screen))
            assert ok
            txt = screen_texts(app.screen)
            assert "!" in txt and today in txt

    run(t())


def test_no_wrap_a_70_colonne(tmp_files):
    async def t():
        today = datetime.now().strftime("%Y-%m-%d")
        app = make_app(
            [
                make_todo(
                    "Titolo abbastanza lungo ma non estremo",
                    todo_id=1,
                    priority=Priority.HIGH,
                    due=today,
                    planned_for=today,
                    stima_pomo=2,
                )
            ]
        )
        app.config["day_window"] = {
            "date": today,
            "start": "09:00",
            "end": "18:00",
            "events": [],
            "allday": [],
        }
        async with app.run_test(size=(70, 20)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            ok = await wait_for(pilot, lambda: "60m" in screen_texts(app.screen))
            assert ok
            from textual.geometry import Region

            lst = app.screen.query_one("#plan-section")
            for line in lst.render_lines(
                Region(0, 0, lst.region.width, lst.region.height)
            ):
                text = "".join(seg.text for seg in line).replace(" ", " ")
                assert len(text) <= lst.region.width

    run(t())
