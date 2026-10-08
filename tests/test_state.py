"""Cambia stato (Space): griglia 2x2, frecce + Enter, esc, focus sul corrente."""

from textual.widgets import Button

from carpediem.lang import T
from tests.conftest import make_app, make_todo, run, screen_texts


def test_space_apre_con_stato_corrente_e_focus(tmp_files):
    async def t():
        app = make_app([make_todo("Da sospendere", todo_id=1, paused=True)])
        app.filter_state = "in_sospeso"
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app._populate_table()
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "StateChoiceScreen"
            txt = screen_texts(app.screen)
            assert "Da sospendere" in txt
            assert T("state_sospeso") in txt  # stato attuale nel titolo
            assert T("state_legend") in txt
            # marker sul corrente, focus sul suo bottone
            sospeso_label = str(app.screen.query_one("#sospeso-btn", Button).label)
            assert sospeso_label.startswith("● ")
            assert getattr(app.screen.focused, "id", None) == "sospeso-btn"
            # niente numeri: solo frecce + Enter
            assert "[1]" not in txt and "[2]" not in txt and "[3]" not in txt

    run(t())


def test_frecce_muovono_enter_sceglie(tmp_files):
    async def t():
        app = make_app([make_todo("A", todo_id=1)])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            await pilot.pause()
            # focus su Attivo (corrente): destra -> Sospeso, Enter sospende
            assert getattr(app.screen.focused, "id", None) == "attivo-btn"
            await pilot.press("right")
            await pilot.pause()
            assert getattr(app.screen.focused, "id", None) == "sospeso-btn"
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ != "StateChoiceScreen"
            assert app.todos[0].paused is True
            # sinistra torna indietro: Attivo <- Sospeso
            app.filter_state = "in_sospeso"
            app._populate_table()
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            await pilot.pause()
            assert getattr(app.screen.focused, "id", None) == "sospeso-btn"
            await pilot.press("left")
            await pilot.pause()
            assert getattr(app.screen.focused, "id", None) == "attivo-btn"
            # giu dalla prima riga: Attivo -> Fatto
            await pilot.press("down")
            await pilot.pause()
            assert getattr(app.screen.focused, "id", None) == "completato-btn"
            # su dalla seconda riga: Fatto -> Attivo
            await pilot.press("up")
            await pilot.pause()
            assert getattr(app.screen.focused, "id", None) == "attivo-btn"
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            assert app.todos[0].done is True

    run(t())


def test_numeri_non_fanno_piu_nulla(tmp_files):
    async def t():
        app = make_app([make_todo("A", todo_id=1)])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            await pilot.pause()
            await pilot.press("3")
            await pilot.pause()
            await pilot.pause()
            # nessun cambio, modale ancora aperta
            assert type(app.screen).__name__ == "StateChoiceScreen"
            assert app.todos[0].state == "attivo"

    run(t())


def test_click_ed_esc(tmp_files):
    async def t():
        app = make_app(
            [make_todo("A", todo_id=1), make_todo("B", todo_id=2, paused=True)]
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            # click su Sospeso per il primo task (attivo)
            await pilot.press("space")
            await pilot.pause()
            await pilot.pause()
            app.screen.query_one("#sospeso-btn", Button).active_effect_duration = 0
            await pilot.click("#sospeso-btn")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ != "StateChoiceScreen"
            by_id = {t.id: t for t in app.todos}
            assert by_id[1].paused is True
            # esc sul secondo (sospeso): nessun cambiamento
            app.filter_state = "in_sospeso"
            app._populate_table()
            await pilot.pause()
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "StateChoiceScreen"
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ != "StateChoiceScreen"
            assert by_id[2].paused is True and by_id[2].done is False

    run(t())
