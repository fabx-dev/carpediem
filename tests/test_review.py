"""Test chiusura giornata: riepilogo, preselezione, conferma piano di domani."""

from datetime import datetime, timedelta

from textual.widgets import SelectionList

import src.main as m
from tests.conftest import make_app, make_todo, run, screen_texts


def _ds(offset: int) -> str:
    return (datetime.now().date() + timedelta(days=offset)).strftime("%Y-%m-%d")


def test_review_riepilogo_e_preselezione(tmp_files):
    async def t():
        today = _ds(0)
        app = make_app(
            [
                make_todo(
                    "Fatto oggi", todo_id=1, done=True, completed_at=today + " 10:00"
                ),
                make_todo("Scaduto", todo_id=2, due=_ds(-2)),
                make_todo("Domani", todo_id=3, due=_ds(1)),
                make_todo("Senza scadenza", todo_id=4),
                make_todo(
                    "Vecchio fatto",
                    todo_id=5,
                    done=True,
                    completed_at="2020-01-01 10:00",
                ),
            ]
        )
        app.todos[1].pomodoro_log.append(today + " 09:00")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_open_review()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "ReviewScreen"
            txt = screen_texts(app.screen)
            assert "1" in txt and "completat" in txt.lower(), txt
            sl = app.screen.query_one(SelectionList)
            # preselezionati i primi 3: scaduto, domani, senza scadenza
            assert sorted(sl.selected) == [2, 3, 4], sl.selected

    run(t())


def test_review_conferma_imposta_domani(tmp_files):
    async def t():
        app = make_app(
            [
                make_todo("A", todo_id=1, due=_ds(-1)),
                make_todo("B", todo_id=2),
                make_todo("C", todo_id=3, planned_for=_ds(1)),
            ]
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_open_review()
            await pilot.pause()
            await pilot.pause()
            sl = app.screen.query_one(SelectionList)
            sl.deselect_all()
            sl.select(2)
            await pilot.pause()
            await pilot.press("ctrl+enter")
            await pilot.pause()
            await pilot.pause()
            by_id = {t.id: t for t in app.todos}
            assert by_id[2].planned_for == _ds(1)
            assert by_id[1].planned_for == ""
            assert by_id[3].planned_for == ""  # deselezionato -> rimosso dal piano
            assert type(app.screen).__name__ != "ReviewScreen"

    run(t())


def test_review_senza_candidati(tmp_files):
    async def t():
        app = make_app(
            [make_todo("Fatto", todo_id=1, done=True, completed_at=_ds(0) + " 10:00")]
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_open_review()
            await pilot.pause()
            await pilot.pause()
            txt = screen_texts(app.screen)
            assert "Niente da pianificare" in txt, txt
            await pilot.press("ctrl+enter")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ != "ReviewScreen"

    run(t())


def test_review_riga_semantica_e_label_senza_id(tmp_files):
    """Riga additiva/sovrascrittiva visibile; label senza #id interni."""
    from src.lang import T as _T

    async def t():
        app = make_app(
            [
                make_todo("A", todo_id=1),
                make_todo("Task [x] con quadre", todo_id=2),
            ]
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_open_review()
            await pilot.pause()
            await pilot.pause()
            txt = screen_texts(app.screen)
            assert _T("rev_additive") in txt
            labels = " ".join(
                str(o.prompt) for o in app.screen.query_one(SelectionList)._options
            )
            assert "#1" not in labels and "#2" not in labels
            # quadre utente rese letterali, non mangiate dal markup
            assert "Task [x] con quadre" in labels

    run(t())


def test_review_notify_con_rimossi_e_esc_no_write(tmp_files):
    """Notify con aggiunti/rimossi; Esc non scrive nulla."""
    from unittest.mock import patch

    from src.lang import T as _T

    async def t():
        app = make_app(
            [
                make_todo("A", todo_id=1, due=_ds(-1)),
                make_todo("B", todo_id=2),
                make_todo("C", todo_id=3, planned_for=_ds(1)),
            ]
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_open_review()
            await pilot.pause()
            await pilot.pause()
            sl = app.screen.query_one(SelectionList)
            sl.deselect_all()
            sl.select(2)
            with patch.object(app, "notify") as mocked:
                await pilot.press("s")
                await pilot.pause()
                await pilot.pause()
            assert type(app.screen).__name__ != "ReviewScreen"
            assert _T("n_rev_saved", n=1, k=1) in str(mocked.call_args)
            by_id = {t.id: t for t in app.todos}
            assert by_id[2].planned_for == _ds(1)
            assert by_id[3].planned_for == ""
            # Esc su riapertura: piano intoccato
            app.action_open_review()
            await pilot.pause()
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()
            assert by_id[2].planned_for == _ds(1)

    run(t())


def test_review_in_menu(tmp_files):
    assert "Chiusura giornata" in [t for t, _, _ in m.CarpeDiemMenuProvider.MENU_IT]


def test_review_layout_terminale_piccolo(tmp_files):
    """Cornice fissa: lista 1fr, Chiudi sempre dentro il box."""
    from textual.widgets import Button

    async def _once(w, h):
        app = make_app([make_todo(f"T-{i}", todo_id=i) for i in range(1, 12)])
        async with app.run_test(size=(w, h)) as pilot:
            await pilot.pause()
            app.action_open_review()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "ReviewScreen"
            box = app.screen.query_one("#rev-box").region
            btn = app.screen.query_one("#rev-close", Button).region
            assert btn.y >= box.y and btn.y + btn.height <= box.y + box.height
            assert btn.x >= box.x and btn.x + btn.width <= box.x + box.width

    async def t():
        for w, h in ((120, 40), (80, 24), (70, 20)):
            await _once(w, h)

    run(t())
