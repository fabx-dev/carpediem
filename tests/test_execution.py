"""Fase 12 — Planning ↔ Pomodoro ↔ Execution (lettura, nessun rescheduling).

- Refresh del piano giorno dopo gli eventi Pomodoro (12.1);
- marker ▶ sul task corrente (12.3, solo presentazione);
- caso E: actual_pomo gia' presente -> nessuna ActualScreen (12.5);
- "pianificato vs eseguito" nel briefing via planner.feedback (12.6).

Non tocca tests/test_ui_regression.py / ui_framework.py (WIP pre-esistenti).
"""

import asyncio
from datetime import datetime, timedelta

import src.screens.plan as plan_mod
from src.lang import T as _T
from tests.conftest import make_app, make_todo, screen_texts


def _day(offset: int) -> str:
    return (datetime.now().date() + timedelta(days=offset)).strftime("%Y-%m-%d")


def _window(day: str, events=None) -> dict:
    return {"date": day, "start": "09:00", "end": "18:00", "events": events or []}


def _label_text(c) -> str:
    labels = c.query("Label")
    if not labels:
        return ""
    w = labels.first()
    content = getattr(w, "content", None)
    if content is None:
        content = getattr(w, "renderable", "")
    return str(content)


async def _open_plan(pilot, app):
    app.action_view_daily_plan()
    await pilot.pause()
    await pilot.pause()
    assert type(app.screen).__name__ == "DailyPlanScreen"


def _planned_rows(app) -> list:
    from textual.widgets import ListView

    lv = app.screen.query_one("#plan-section", ListView)
    return [
        c
        for c in lv.children
        if isinstance(c, plan_mod.PlanRow) and c.section == "planned"
    ]


# --- 12.1: refresh del piano dopo gli eventi Pomodoro -----------------------


def test_refresh_piano_dopo_focus_completato(tmp_files):
    """o sul piano -> X nel popup (che si chiude da solo) -> il pomodoro e'
    accreditato e la riga del piano mostra 🍅 aggiornata senza ulteriori
    interazioni."""

    async def t():
        app = make_app(
            [
                make_todo("A", todo_id=1, planned_for=_day(0), stima_pomo=1),
            ]
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            assert "🍅0/1" in screen_texts(app.screen)
            await pilot.press("o")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "PomodoroScreen"
            await pilot.press("x")  # completa il focus (credito + break, chiude popup)
            await pilot.pause()
            await pilot.pause()
            assert app.store.by_id(1).pomodoros == 1
            assert type(app.screen).__name__ == "DailyPlanScreen"
            # Ricomposizione avvenuta: il conteggio nella riga e' aggiornato.
            assert "🍅1/1" in screen_texts(app.screen)

    asyncio.run(t())


def test_refresh_piano_dopo_stop(tmp_files):
    async def t():
        app = make_app([make_todo("A", todo_id=1, planned_for=_day(0))])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            await pilot.press("o")
            await pilot.pause()
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "DailyPlanScreen"
            assert "▶" in screen_texts(app.screen)
            app._pomodoro_stop()
            await pilot.pause()
            await pilot.pause()
            # Nessun credito (D1) e marker sparito dopo la ricomposizione.
            assert app.store.by_id(1).pomodoros == 0
            assert "▶" not in screen_texts(app.screen)

    asyncio.run(t())


def test_refresh_piano_dopo_fine_break(tmp_files):
    async def t():
        app = make_app([make_todo("A", todo_id=1, planned_for=_day(0))])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            await pilot.press("o")
            await pilot.pause()
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()
            app._finish_break(skipped=True)  # fine/skip break -> stato pulito
            await pilot.pause()
            await pilot.pause()
            assert app.focus_task_id is None
            assert "▶" not in screen_texts(app.screen)

    asyncio.run(t())


def test_refresh_preserva_highlight(tmp_files):
    async def t():
        app = make_app(
            [
                make_todo("A", todo_id=1, planned_for=_day(0)),
                make_todo("B", todo_id=2, planned_for=_day(0)),
            ]
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            await pilot.press("o")  # avvia sul primo
            await pilot.pause()
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()
            rows = _planned_rows(app)
            from textual.widgets import ListView

            lv = app.screen.query_one("#plan-section", ListView)
            lv.index = list(lv.children).index(rows[1])  # evidenzia B
            await pilot.pause()
            app._complete_focus()  # evento: credito su A + break
            await pilot.pause()
            await pilot.pause()
            # La ricomposizione ricrea la ListView: richiedila allo screen.
            lv2 = app.screen.query_one("#plan-section", ListView)
            item = lv2.highlighted_child
            assert getattr(item, "task_id", None) == 2

    asyncio.run(t())


# --- 12.3: marker del task corrente ----------------------------------------


def test_marker_sul_task_corrente(tmp_files):
    async def t():
        app = make_app(
            [
                make_todo("A", todo_id=1, planned_for=_day(0)),
                make_todo("B", todo_id=2, planned_for=_day(0)),
            ]
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            assert "▶" not in screen_texts(app.screen)  # nessun timer
            await pilot.press("o")
            await pilot.pause()
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()
            rows = _planned_rows(app)
            texts = [_label_text(r) for r in rows]
            assert any("▶" in x for x in texts)
            # Solo il task in esecuzione ha il marker.
            marked = [x for x in texts if "▶" in x]
            assert len(marked) == 1 and "A" in marked[0]

    asyncio.run(t())


def test_marker_nessun_timer(tmp_files):
    async def t():
        app = make_app([make_todo("A", todo_id=1, planned_for=_day(0), stima_pomo=1)])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            txt = screen_texts(app.screen)
            assert "▶" not in txt
            assert "🍅0/1" in txt

    asyncio.run(t())


# --- 12.5: caso E — actual_pomo gia' presente -------------------------------


def test_nessuna_actualscreen_con_actual_presente(tmp_files):
    async def t():
        app = make_app(
            [
                make_todo(
                    "A", todo_id=1, planned_for=_day(0), stima_pomo=2, actual_pomo=3
                ),
            ]
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            app.screen._ask_actual(1, "planned")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ != "ActualScreen"
            assert type(app.screen).__name__ == "DailyPlanScreen"

    asyncio.run(t())


# --- 12.6: pianificato vs eseguito nel briefing -----------------------------


async def _open_briefing(pilot, app):
    app.action_briefing_evening()
    await pilot.pause()
    await pilot.pause()
    assert type(app.screen).__name__ == "BriefingScreen"


def test_briefing_exec_con_finestra(tmp_files):
    async def t():
        todos = [
            make_todo(
                "A", todo_id=1, planned_for=_day(0), stima_pomo=1, pomodoro_log=[]
            ),
            make_todo("B", todo_id=2, planned_for=_day(0), stima_pomo=2),
        ]
        app = make_app(todos)
        app.store.by_id(1).pomodoros = 2  # A eseguito piu' della stima
        app.store.by_id(1).actual_pomo = 3  # dichiarazione utente
        app.store.by_id(1).done = True  # completato
        app.config["day_window"] = _window(_day(0))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_briefing(pilot, app)
            txt = screen_texts(app.screen)
            assert _T("brief_e_sec_exec") in txt
            # B (attivo): slot dello Scheduler (2 🍅 = 1h); A (completato):
            # senza slot, con stima/sessioni/actual/stato.
            assert "09:00–10:00 B" in txt
            assert "stima 2 🍅" in txt
            assert "attivo" in txt
            # A: stima, sessioni, actual, stato — mai un orario.
            assert "A — stima 1 🍅 · eseguite 2 🍅 · actual 3 · completato" in txt
            assert "09:00–09:30 A" not in txt and "10:00–10:30 A" not in txt

    asyncio.run(t())


def test_briefing_exec_senza_finestra_niente_slot(tmp_files):
    async def t():
        app = make_app([make_todo("A", todo_id=1, planned_for=_day(0), stima_pomo=1)])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_briefing(pilot, app)
            txt = screen_texts(app.screen)
            assert _T("brief_e_sec_exec") in txt
            assert "A" in txt
            assert "09:00–" not in txt  # nessun orario inventato
            assert "stima 1 🍅" in txt and "eseguite 0 🍅" in txt

    asyncio.run(t())


def test_briefing_exec_nessun_confermato_nessuna_sezione(tmp_files):
    async def t():
        app = make_app([make_todo("A", todo_id=1)])  # non pianificato
        app.config["day_window"] = _window(_day(0))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_briefing(pilot, app)
            assert _T("brief_e_sec_exec") not in screen_texts(app.screen)

    asyncio.run(t())


def test_briefing_exec_completamento_manuale_senza_sessioni(tmp_files):
    """Caso D: completato via Space senza pomodoro -> riga con 0 sessioni."""

    async def t():
        app = make_app([make_todo("A", todo_id=1, planned_for=_day(0), stima_pomo=1)])
        app.store.by_id(1).done = True
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_briefing(pilot, app)
            txt = screen_texts(app.screen)
            assert _T("brief_e_sec_exec") in txt
            assert "eseguite 0 🍅" in txt
            assert "completato" in txt

    asyncio.run(t())


def test_briefing_exec_layout_piccolo(tmp_files):
    async def t():
        for size in ((120, 40), (80, 24), (70, 20)):
            app = make_app(
                [
                    make_todo("A", todo_id=1, planned_for=_day(0), stima_pomo=1),
                    make_todo("B", todo_id=2, planned_for=_day(0), stima_pomo=2),
                ]
            )
            app.config["day_window"] = _window(_day(0))
            async with app.run_test(size=size) as pilot:
                await pilot.pause()
                await _open_briefing(pilot, app)
                from textual.widgets import Button

                box = app.screen.query_one("#brief-box").region
                close = app.screen.query_one("#brief-close", Button).region
                assert close.y + close.height <= box.y + box.height, size

    asyncio.run(t())


def test_briefing_exec_stampa_include_sezione(tmp_files):
    async def t():
        app = make_app([make_todo("A", todo_id=1, planned_for=_day(0), stima_pomo=1)])
        app.config["day_window"] = _window(_day(0))
        captured = {}

        def on_print(m, day, text):
            captured["text"] = text
            return "/tmp/exec.md"

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_briefing(pilot, app)
            app.screen.on_print = on_print
            app.screen._print()
            # La stampa è plain (senza markup): la sezione compare senza tag.
            assert "Pianificato vs eseguito" in captured.get("text", "")

    asyncio.run(t())
