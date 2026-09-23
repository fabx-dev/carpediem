"""Buongiorno <-> Outlook (B3): bottone, merge, setup, gate — con hook finti.

Mai rete/auth reali: gli hook iniettati ritornano dict (stesso protocollo
dei callback di app). Copre: bottone senza hook, fetch->merge->conferma
con persistenza day_window (eventi+allday), setup_needed->setup->annulla,
connect->poll->salvataggio+ricarica, gate lock, merge puro.
"""

import src.screens.plan as plan_mod
from src.screens._shared import outlook_error_text
from tests.conftest import make_app, make_todo, run, screen_texts, wait_for

IT = "m.rossi@azienda.it"
EVENTS = [("10:00", "11:00", "Riunione"), ("13:00", "14:00", "Pranzo")]


def _todos():
    return [make_todo("A", todo_id=1), make_todo("B", todo_id=2)]


def _hooks(**kw):
    base = dict(
        fetch=None,
        state=None,
        save=None,
        merge=None,
        connect=None,
        poll=None,
        unlink=None,
    )
    base.update(kw)
    return plan_mod.OutlookHooks(**base)


def _fetch_ok():
    def fetch():
        return {
            "ok": True,
            "events": list(EVENTS),
            "allday": ["Ferragosto"],
            "skipped": ["X"],
            "adopted": IT,
        }

    return fetch


async def _open_buongiorno(pilot, app, hooks=None):
    app.action_plan_day()
    await pilot.pause()
    await pilot.pause()
    if hooks is not None:
        app.screen.outlook_hooks = hooks


def test_merge_outlook_lines_puro():
    m = plan_mod.merge_outlook_lines
    assert m("", EVENTS) == "10:00-11:00 Riunione\n13:00-14:00 Pranzo"
    # Mai duplicati (match esatto), mai replace del manuale.
    assert m("09:00-09:30 Standup\n10:00-11:00 Riunione", EVENTS) == (
        "09:00-09:30 Standup\n10:00-11:00 Riunione\n13:00-14:00 Pranzo"
    )
    # Titoli multilinea sanificati, orari invalidi saltati.
    assert m("", [("9", "10", "X"), ("10:00", "11:00", "A\nB")]) == "10:00-11:00 A B"


def test_bottone_senza_hook_avviso(tmp_files):
    async def t():
        app = make_app(_todos())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_buongiorno(pilot, app)
            await pilot.press("o")
            await pilot.pause()
            assert type(app.screen).__name__ == "PlanProposalScreen"

    run(t())


def test_fetch_compila_e_conferma_persiste(tmp_files):
    saved = {}

    async def t():
        from textual.widgets import Input

        app = make_app(_todos())
        hooks = _hooks(fetch=_fetch_ok(), merge=lambda p: saved.update(p))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_buongiorno(pilot, app, hooks)
            scr = app.screen
            scr.query_one("#planp-start", Input).value = "09:00"
            scr.query_one("#planp-end", Input).value = "18:00"
            await pilot.pause()
            await pilot.press("o")
            ok = await wait_for(
                pilot, lambda: "Riunione" in scr.query_one("#planp-events").text
            )
            assert ok
            txt = screen_texts(scr)
            assert "10:00–11:00 IMPEGNO: Riunione" in txt
            assert "Tutto il giorno: Ferragosto" in txt
            assert saved.get("account") == IT
            await pilot.press("s")
            await pilot.pause()
            await pilot.pause()
            win = app.config.get("day_window")
            assert win["events"] == [
                {"start": "10:00", "end": "11:00", "title": "Riunione"},
                {"start": "13:00", "end": "14:00", "title": "Pranzo"},
            ]
            assert win["allday"] == ["Ferragosto"]

    run(t())


def test_setup_needed_apre_config_e_annulla_non_scrive(tmp_files):
    async def t():
        app = make_app(_todos())
        hooks = _hooks(
            fetch=lambda: {"ok": False, "code": "setup_needed"},
            state=lambda: {"config": None, "has_token": False},
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_buongiorno(pilot, app, hooks)
            await pilot.press("o")
            ok = await wait_for(
                pilot, lambda: type(app.screen).__name__ == "OutlookSetupScreen"
            )
            assert ok
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "PlanProposalScreen"
            assert app.config.get("outlook") is None
            assert app.config.get("day_window") is None

    run(t())


def test_setup_connect_salva_e_ricarica(tmp_files):
    calls = {"n_fetch": 0}
    stored = {}

    def fetch():
        calls["n_fetch"] += 1
        if calls["n_fetch"] == 1:
            return {"ok": False, "code": "setup_needed"}
        return {
            "ok": True,
            "events": list(EVENTS),
            "allday": [],
            "skipped": [],
            "adopted": IT,
        }

    async def t():
        from textual.widgets import Input

        app = make_app(_todos())
        hooks = _hooks(
            fetch=fetch,
            state=lambda: {"config": stored.get("cfg"), "has_token": False},
            save=lambda cfg: stored.update(cfg=cfg),
            merge=lambda p: None,
            connect=lambda cfg: {
                "ok": True,
                "uri": "https://microsoft.com/x",
                "code": "AB1",
                "flow": {"f": 1},
            },
            poll=lambda flow: {"ok": True, "username": IT},
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_buongiorno(pilot, app, hooks)
            await pilot.press("o")
            ok = await wait_for(
                pilot, lambda: type(app.screen).__name__ == "OutlookSetupScreen"
            )
            assert ok
            scr = app.screen
            scr.query_one("#outlook-client", Input).value = "cid-123"
            scr.query_one("#outlook-tenant", Input).value = "tid-456"
            scr.query_one("#outlook-account", Input).value = IT
            await pilot.click("#outlook-connect")
            ok = await wait_for(
                pilot, lambda: type(app.screen).__name__ == "PlanProposalScreen"
            )
            assert ok
            assert stored["cfg"]["account"] == IT
            # Auto-ricarica dopo il collegamento: secondo fetch compila.
            ok = await wait_for(
                pilot,
                lambda: "Riunione" in app.screen.query_one("#planp-events").text,
            )
            assert ok

    run(t())


def test_gate_lock_blocca_fetch(tmp_files):
    from src import crypto as crypto_mod

    app = make_app(_todos())
    assert app._outlook_fetch_sync() == {"ok": False, "code": "need_lock"}
    crypto_mod.set_key(b"fake-test-key")
    try:
        assert app._outlook_fetch_sync() == {"ok": False, "code": "setup_needed"}
    finally:
        crypto_mod.set_key(None)


def test_outlook_error_text_mapping():
    assert "cifratura" in outlook_error_text("need_lock")
    assert "IT" in outlook_error_text("admin_consent")
    assert "xyz" in outlook_error_text("sconosciuto", "xyz")
