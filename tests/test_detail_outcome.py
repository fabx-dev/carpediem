"""Why della card rispetta l'outcome: mai "Confermato" senza slot.

Casi: schedulato -> "Nel piano"; ELIGIBLE -> cornice non-inserito;
OUTSIDE -> cornice non-entra-oggi; overdue+obbligatorio+non-inserito
(caso reale); nessun outcome -> fallback legacy invariato.
"""

from datetime import datetime, timedelta

import pytest

from carpediem.lang import T as _T
from carpediem.models import Priority
from tests.conftest import make_app, make_todo, run, screen_texts


@pytest.fixture(autouse=True)
def _buongiorno_al_mattino(monkeypatch):
    """F1 clip-a-now: congela l'ora alle 08:00 di oggi (scenari mattutini)."""
    import carpediem.screens.plan as plan_mod

    fixed = datetime.strptime(f"{_day(0)} 08:00", "%Y-%m-%d %H:%M")

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

    monkeypatch.setattr(plan_mod, "datetime", _Frozen)


def _day(offset: int) -> str:
    return (datetime.now().date() + timedelta(days=offset)).strftime("%Y-%m-%d")


def _window(start="09:00", end="09:30"):
    return {"date": _day(0), "start": start, "end": end, "events": []}


async def _open_plan(pilot, app):
    app.action_view_daily_plan()
    await pilot.pause()
    await pilot.pause()
    assert type(app.screen).__name__ == "DailyPlanScreen"


async def _open_detail(pilot, app, tid):
    for _ in range(30):
        if app.screen._current()[0] == tid:
            break
        await pilot.press("down")
        await pilot.pause()
    await pilot.press("enter")
    await pilot.pause()
    await pilot.pause()
    assert type(app.screen).__name__ == "DetailScreen"
    return screen_texts(app.screen)


def test_1_schedulato_puo_dire_nel_piano(tmp_files):
    async def t():
        app = make_app(
            [
                make_todo("A", todo_id=1, planned_for=_day(0)),
                make_todo("B", todo_id=2, planned_for=_day(0)),
            ]
        )
        app.config["day_window"] = _window()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            txt = await _open_detail(pilot, app, 1)  # A con slot
            assert _T("why_scheduled") in txt
            assert _T("why_scheduled_noslot_tasks") not in txt
            assert _T("why_scheduled_noslot_outside") not in txt

    run(t())


def test_2_eligible_non_dice_confermato(tmp_files):
    async def t():
        app = make_app(
            [
                make_todo("A", todo_id=1, planned_for=_day(0)),
                make_todo("B", todo_id=2, planned_for=_day(0)),
            ]
        )
        app.config["day_window"] = _window()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            txt = await _open_detail(pilot, app, 2)  # B senza slot, gara persa
            assert "Confermato" not in txt
            assert _T("why_scheduled") not in txt
            assert (
                _T(
                    "why_noslot_sentence_tasks",
                    m=_T("why_frag_m_planned"),
                    c=_T("why_frag_c_tasks", t="A"),
                )
                in txt
            )

    run(t())


def test_3_outside_non_dice_confermato(tmp_files):
    async def t():
        app = make_app(
            [
                make_todo("A", todo_id=1, planned_for=_day(0)),
                make_todo("Big", todo_id=3, planned_for=_day(0), stima_pomo=3),
            ]
        )
        app.config["day_window"] = _window()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            txt = await _open_detail(pilot, app, 3)  # Big 90m in 30m
            assert "Confermato" not in txt
            assert (
                _T(
                    "why_noslot_sentence_outside",
                    m=_T("why_frag_m_planned"),
                    c=_T("why_frag_c_window_gap", g=30, n=90),
                )
                in txt
            )

    run(t())


def test_4_ritardo_obbligatorio_non_inserito(tmp_files):
    """Caso reale: overdue + priorita' obbligatoria ma gara persa."""

    async def t():
        app = make_app(
            [
                make_todo(
                    "A",
                    todo_id=1,
                    planned_for=_day(0),
                    due=_day(-1),
                    project="vecchio",
                    created="2026-01-01",
                ),
                make_todo(
                    "X",
                    todo_id=2,
                    planned_for=_day(0),
                    due=_day(-1),
                    priority=Priority.HIGH,
                ),
            ]
        )
        app.config["day_window"] = _window()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            txt = screen_texts(app.screen)
            assert "09:00–09:30 A" in txt  # A vince (stale), X resta fuori
            txt = await _open_detail(pilot, app, 2)
            assert "Confermato" not in txt  # mai "confermato" senza slot
            assert (
                _T(
                    "why_noslot_sentence_tasks",
                    m=_T("why_frag_m_overdue"),
                    c=_T("why_frag_c_tasks", t="A"),
                )
                in txt
            )
            # Motivi restano visibili (primary assorbito, dettagli fattuali):
            assert _T("why_story_sched_overdue") not in txt  # story soppressa
            assert _T("why_sec_details") in txt
            assert _T("why_ev_due", d=_day(-1)) in txt

    run(t())


def test_5_senza_outcome_fallback_invariato(tmp_files):
    """Detail senza alternatives: legacy, 'Nel piano' come prima."""
    from carpediem.screens.views import DetailScreen

    async def t():
        app = make_app([make_todo("A", todo_id=1, planned_for=_day(0))])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.push_screen(
                DetailScreen(
                    app.todos[0],
                    app.todos,
                    today=_day(0),
                    hours=6.0,
                )
            )
            await pilot.pause()
            await pilot.pause()
            txt = screen_texts(app.screen)
            assert _T("why_scheduled") in txt

    run(t())
