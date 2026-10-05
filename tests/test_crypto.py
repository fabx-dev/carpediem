"""Test cifratura: envelope, lock, enable/change/disable, backup cifrato."""

import asyncio

import pytest

import src.main as m
from src import crypto as crypto_mod
from tests.conftest import make_app, make_todo


@pytest.fixture()
def locked_down():
    crypto_mod.set_key(None)
    yield
    crypto_mod.set_key(None)


def test_envelope_roundtrip_e_wrong_password(locked_down):
    crypto_mod.set_key(crypto_mod.encode_password("segreta12"))
    enc = crypto_mod.protect_text('{"a": 1}')
    assert crypto_mod.is_envelope(enc)
    obj, was = crypto_mod.unprotect_text(enc)
    assert (obj, was) == ({"a": 1}, True)
    assert not crypto_mod.is_envelope('{"a": 1}')
    crypto_mod.set_key(crypto_mod.encode_password("sbagliata"))
    try:
        crypto_mod.unprotect_text(enc)
    except ValueError:
        pass
    else:
        raise AssertionError("doveva fallire")
    crypto_mod.set_key(None)
    assert crypto_mod.protect_text('{"a": 1}') == '{"a": 1}'
    try:
        crypto_mod.unprotect_text(enc)
    except ValueError:
        pass
    else:
        raise AssertionError("doveva fallire senza chiave")


def test_save_load_cifrati(tmp_files, locked_down):
    crypto_mod.set_key(crypto_mod.encode_password("segreta12"))
    todos = [m.TodoItem(title="Segreto", todo_id=1)]
    m._save_todos_plain(todos)
    raw = m.DATA_FILE.read_text(encoding="utf-8")
    assert crypto_mod.is_envelope(raw) and "Segreto" not in raw
    back = m.load_todos()
    assert [t.title for t in back] == ["Segreto"]
    crypto_mod.set_key(None)
    assert m.load_todos() == []


def test_cambio_chiave_commit_non_perde_item(tmp_files, locked_down):
    from src.store import TodoStore

    crypto_mod.set_key(crypto_mod.encode_password("vecchia"))
    m._save_todos_plain([make_todo("A", todo_id=1)])
    s = TodoStore.load()  # chiave corrente ok -> base e memoria = [A]
    crypto_mod.set_key(crypto_mod.encode_password("nuova"))
    # Il disco e' ora illeggibile: solo il path cambio-password (memoria
    # autorevole, force_rewrite) puo' riscriverlo, mai il commit normale.
    s.commit(force_rewrite=True)
    assert [t.title for t in m.load_todos()] == ["A"]
    crypto_mod.set_key(None)
    # senza chiave il file resta un envelope (non e' stato toccato in chiaro)
    assert not crypto_mod.is_unlocked()
    assert m.load_todos() == []


def test_enable_change_disable(tmp_files, locked_down):
    async def t():
        app = make_app([make_todo("A")])
        app._save_data()
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            # enable
            app.push_screen(
                m.PasswordScreen(
                    "sec_pw_title_enable",
                    ["sec_pw_new", "sec_pw_repeat"],
                    app._pw_valid_new,
                ),
                app._sec_enable,
            )
            await pilot.pause()
            await pilot.pause()
            from textual.widgets import Input

            app.screen.query_one("#pw-0", Input).value = "corta"
            app.screen.query_one("#pw-1", Input).value = "corta"
            await pilot.press("ctrl+enter")
            await pilot.pause()
            assert isinstance(app.screen, m.PasswordScreen), (
                "corta rifiutata, resta aperto"
            )
            app.screen.query_one("#pw-0", Input).value = "segreta12"
            app.screen.query_one("#pw-1", Input).value = "diversa"
            await pilot.press("ctrl+enter")
            await pilot.pause()
            assert isinstance(app.screen, m.PasswordScreen), "mismatch resta aperto"
            app.screen.query_one("#pw-0", Input).value = "segreta12"
            app.screen.query_one("#pw-1", Input).value = "segreta12"
            await pilot.press("ctrl+enter")
            await pilot.pause()
            await pilot.pause()
            assert crypto_mod.is_unlocked()
            raw = m.DATA_FILE.read_text(encoding="utf-8")
            assert (
                crypto_mod.is_envelope(raw)
                and "Segreto" not in raw
                and '"A"' not in raw
            )
            print("enable: OK")
            # change con vecchia errata
            app.push_screen(
                m.PasswordScreen(
                    "sec_pw_title_change",
                    ["sec_pw_current", "sec_pw_new", "sec_pw_repeat"],
                    app._pw_valid_change,
                ),
                app._sec_change,
            )
            await pilot.pause()
            await pilot.pause()
            app.screen.query_one("#pw-0", Input).value = "sbagliata"
            app.screen.query_one("#pw-1", Input).value = "nuova123"
            app.screen.query_one("#pw-2", Input).value = "nuova123"
            await pilot.press("ctrl+enter")
            await pilot.pause()
            assert isinstance(app.screen, m.PasswordScreen)
            print("change vecchia errata: OK")
            app.screen.query_one("#pw-0", Input).value = "segreta12"
            await pilot.press("ctrl+enter")
            await pilot.pause()
            await pilot.pause()
            assert crypto_mod.is_unlocked()
            print("change: OK")
            # disable
            app.push_screen(
                m.PasswordScreen(
                    "sec_pw_title_disable",
                    ["sec_pw_current"],
                    app._pw_valid_disable,
                ),
                app._sec_disable,
            )
            await pilot.pause()
            await pilot.pause()
            app.screen.query_one("#pw-0", Input).value = "nuova123"
            await pilot.press("ctrl+enter")
            await pilot.pause()
            await pilot.pause()
            assert not crypto_mod.is_unlocked()
            assert not crypto_mod.is_envelope(m.DATA_FILE.read_text(encoding="utf-8"))
            assert [t.title for t in m.load_todos()] == ["A"]
            print("disable: OK")

    asyncio.run(t())


def test_lock_startup_e_backup_cifrato(tmp_files, locked_down):
    # dati cifrati reali su disco (come dopo enable)
    crypto_mod.set_key(crypto_mod.encode_password("segreta12"))
    m._save_todos_plain([make_todo("A")])
    crypto_mod.set_key(None)
    assert m._needs_unlock()

    async def t():
        from textual.widgets import Input

        app = m.TodoApp()  # parte bloccata: non legge nulla
        assert app.todos == []
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "LockScreen"
            # backup contiene cifrato
            p = m.create_backup()
            import zipfile

            with zipfile.ZipFile(p) as zf:
                assert crypto_mod.is_envelope(zf.read("todos.json").decode("utf-8"))
            print("backup cifrato: OK")
            # password errata
            app.screen.query_one("#lock-pw", Input).value = "nope"
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "LockScreen"
            assert app.todos == []
            print("lock rifiuta: OK")
            # corretta (attendi la riabilitazione del campo dopo l'errore)
            from tests.conftest import wait_for

            assert await wait_for(
                pilot,
                lambda: not app.screen.query_one("#lock-pw", Input).disabled,
                tries=60,
                delay=0.05,
            )
            app.screen.query_one("#lock-pw", Input).value = "segreta12"
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            await pilot.pause()
            assert [t.title for t in app.todos] == ["A"], [t.title for t in app.todos]
            print("lock sblocca e carica: OK")

    asyncio.run(t())
