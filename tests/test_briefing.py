"""Resoconto sera: composizione dati esistenti (isolati).

La ex voce mattutina e' confluita in Buongiorno (PlanProposalScreen, tasto P):
i test della proposta unificata vivono in test_plan_ui.py.
"""

import asyncio
from datetime import datetime, timedelta

from src.lang import T
from tests.conftest import commands_module, make_app, make_todo, screen_texts


def _day(offset: int) -> str:
    return (datetime.now().date() + timedelta(days=offset)).strftime("%Y-%m-%d")


def _todos():
    return [
        make_todo("P-piano", todo_id=1, planned_for=_day(0), stima_pomo=2),
        make_todo("D-oggi", todo_id=2, due=_day(0)),
        make_todo("O-ieri", todo_id=3, due=_day(-1)),
        make_todo(
            "Y-fatto",
            todo_id=4,
            done=True,
            completed_at=_day(-1) + " 10:00",
            pomodoro_log=[_day(-1) + " 10:30"],
        ),
    ]


def test_sera(tmp_files):
    async def t():
        todos = _todos() + [
            make_todo("F-oggi", todo_id=5, done=True, completed_at=_day(0) + " 09:00"),
            make_todo(
                "G-oggi",
                todo_id=6,
                done=True,
                completed_at=_day(0) + " 11:00",
                pomodoro_log=[_day(0) + " 11:30"],
            ),
        ]
        app = make_app(todos)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_briefing_evening()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "BriefingScreen"
            txt = screen_texts(app.screen)
            assert T("brief_e_sec_done") in txt
            assert "2/5 · 1 🍅  ████░░░░░░" in txt  # barra obiettivo
            assert T("brief_e_sec_left") in txt
            assert "P-piano" in txt  # rimasto in piano
            assert "#1" not in txt  # niente id interni
            assert T("brief_e_hint") in txt
            # hint fuori dallo scroll: widget fisso dedicato
            app.screen.query_one("#brief-hint")
            from textual.widgets import Button

            box = app.screen.query_one("#brief-box").region
            for bid in ("#brief-print", "#brief-goto", "#brief-close"):
                r = app.screen.query_one(bid, Button).region
                assert r.x >= box.x and r.x + r.width <= box.x + box.width
                assert r.y >= box.y and r.y + r.height <= box.y + box.height

    asyncio.run(t())


def test_ponte_verso_chiusura(tmp_files):
    """Bottone Vai alla Chiusura: chiude il Resoconto e apre la Chiusura."""
    from textual.widgets import Button

    async def t():
        app = make_app(_todos())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_briefing_evening()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "BriefingScreen"
            app.screen.query_one("#brief-goto", Button).active_effect_duration = 0
            await pilot.click("#brief-goto")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "ReviewScreen"

    asyncio.run(t())


def test_layout_terminale_piccolo(tmp_files):
    """Hint e bottoni fissi: tutto dentro la cornice anche a 80x24."""

    async def t():
        todos = _todos() + [
            make_todo(f"Rimasto-{i}", todo_id=10 + i, planned_for=_day(0))
            for i in range(8)
        ]
        app = make_app(todos)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            app.action_briefing_evening()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "BriefingScreen"
            box = app.screen.query_one("#brief-box").region
            for bid in ("#brief-hint", "#brief-print", "#brief-goto", "#brief-close"):
                r = app.screen.query_one(bid).region
                assert r.y >= box.y and r.y + r.height <= box.y + box.height

    asyncio.run(t())


def test_stampa_sera(tmp_files, monkeypatch, tmp_path):
    """Tasto p / bottone Stampa: file Markdown senza markup, id isolati."""
    from pathlib import Path as _P

    monkeypatch.setenv("TASKO_HOME", str(tmp_path / "home"))

    async def t():
        app = make_app(_todos())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_briefing_evening()
            await pilot.pause()
            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()
            out = _P(str(tmp_path / "home")) / "CarpeDiem_screenshots"
            files = sorted(out.glob("carpediem_briefing_evening_*.md"))
            assert len(files) == 1
            text = files[0].read_text(encoding="utf-8")
            assert T("brief_e_title", date=_day(0)) in text
            assert "P-piano" in text
            assert "[b]" not in text and "[dim]" not in text
            # i titoli con [] utente resterebbero: nessun tag noto rimasto
            assert "[green]" not in text
            # l'hint di navigazione non finisce nel documento
            assert "Chiudi qui" not in text

    asyncio.run(t())


def test_vuoto_e_menu(tmp_files):
    names = [action for _t, _h, action in commands_module.CarpeDiemMenuProvider.MENU_IT]
    assert "action_briefing_evening" in names
    assert "action_briefing_morning" not in names
    assert "action_plan_day" in names

    async def t():
        app = make_app([])
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.pause()
            app.action_briefing_evening()
            await pilot.pause()
            await pilot.pause()
            # mai pianificato: messaggio onesto, non congratulazioni
            assert T("brief_e_left_never") in screen_texts(app.screen)

    asyncio.run(t())


def test_vuoto_piano_svuotato(tmp_files):
    """Tutto fatto ma c'era un piano: congratulazioni vere."""

    async def t():
        app = make_app(
            [
                make_todo(
                    "Fatto",
                    todo_id=1,
                    done=True,
                    completed_at=_day(0) + " 09:00",
                    planned_for=_day(0),
                )
            ]
        )
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.pause()
            app.action_briefing_evening()
            await pilot.pause()
            await pilot.pause()
            assert T("brief_e_left_empty") in screen_texts(app.screen)

    asyncio.run(t())
