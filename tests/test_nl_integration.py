"""Integrazione NL Sprint 2: form (ctrl+l) + CLI add (file isolati)."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path as _P

from textual.widgets import Input, Label, Select

from carpediem.models import Priority, Recurrence
from tests.conftest import make_app

PHRASE = "Report *lavoro #ufficio !1 ~2 2026-12-01 09:30"


def test_form_ctrl_l_compila_e_anteprima(tmp_files):
    async def t():
        app = make_app([])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_new_todo()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "TodoFormScreen"
            app.screen.query_one("#title-input", Input).value = PHRASE
            await pilot.press("ctrl+l")
            await pilot.pause()
            scr = app.screen
            assert scr.query_one("#title-input", Input).value == "Report"
            assert scr.query_one("#due-input", Input).value == "2026-12-01 09:30"
            assert scr.query_one("#project-input", Input).value == "lavoro"
            assert scr.query_one("#tags-input", Input).value == "ufficio"
            assert scr.query_one("#stima-input", Input).value == "2"
            assert scr.query_one("#priority-select", Select).value == Priority.HIGH
            assert scr.query_one("#recurrence-select", Select).value == Recurrence.NONE
            preview = str(scr.query_one("#nl-preview", Label).render())
            assert "2026-12-01 09:30" in preview
            assert "*lavoro" in preview and "#ufficio" in preview
            await pilot.press("ctrl+enter")
            await pilot.pause()
            await pilot.pause()
            assert len(app.todos) == 1
            todo = app.todos[0]
            assert todo.title == "Report"
            assert todo.due == "2026-12-01 09:30"
            assert todo.project == "lavoro"
            assert todo.tags == ["ufficio"]
            assert todo.priority == Priority.HIGH
            assert todo.stima_pomo == 2

    asyncio.run(t())


def test_form_salva_con_s(tmp_files):
    """Tasto s (terminal-safe) salva come ctrl+enter (focus fuori dai campi)."""
    from textual.widgets import Button

    async def t():
        app = make_app([])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_new_todo()
            await pilot.pause()
            await pilot.pause()
            app.screen.query_one("#title-input", Input).value = "Solo titolo"
            app.screen.query_one("#save-btn", Button).focus()
            await pilot.press("s")
            await pilot.pause()
            await pilot.pause()
            assert len(app.todos) == 1
            assert app.todos[0].title == "Solo titolo"

    asyncio.run(t())


def test_form_ctrl_l_titolo_vuoto_apre_aiuto(tmp_files):
    async def t():
        app = make_app([])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_new_todo()
            await pilot.pause()
            await pilot.pause()
            await pilot.press("ctrl+l")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "NLHelpScreen"
            await pilot.press("escape")
            await pilot.pause()
            assert type(app.screen).__name__ == "TodoFormScreen"

    asyncio.run(t())


def test_form_ctrl_l_merge_non_overwrite(tmp_files):
    """Campi digitati a mano sopravvivono al fill (solo trovati compilati)."""

    async def t():
        app = make_app([])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_new_todo()
            await pilot.pause()
            await pilot.pause()
            scr = app.screen
            scr.query_one("#project-input", Input).value = "casa"
            scr.query_one("#title-input", Input).value = "call domani"
            await pilot.press("ctrl+l")
            await pilot.pause()
            from datetime import datetime, timedelta

            domani = (datetime.now().date() + timedelta(days=1)).strftime("%Y-%m-%d")
            assert scr.query_one("#title-input", Input).value == "call"
            assert scr.query_one("#due-input", Input).value == domani
            assert scr.query_one("#project-input", Input).value == "casa"
            # secondo ctrl+l: idempotente, niente reset
            await pilot.press("ctrl+l")
            await pilot.pause()
            assert scr.query_one("#due-input", Input).value == domani
            assert scr.query_one("#project-input", Input).value == "casa"
            from carpediem.models import Priority as _P

            assert scr.query_one("#priority-select", Select).value == _P.MEDIUM

    asyncio.run(t())


def test_form_ctrl_l_focus_e_note(tmp_files):
    """Dopo il fill il focus va su Salva (s non corrompe il titolo); // in nota."""
    from textual.widgets import TextArea

    async def t():
        app = make_app([])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_new_todo()
            await pilot.pause()
            await pilot.pause()
            scr = app.screen
            scr.query_one("#title-input", Input).value = "call domani // portare doc"
            await pilot.press("ctrl+l")
            await pilot.pause()
            assert scr.query_one("#notes-textarea", TextArea).text == "portare doc"
            assert scr.focused is scr.query_one("#save-btn")
            await pilot.press("s")
            await pilot.pause()
            await pilot.pause()
            assert len(app.todos) == 1
            assert app.todos[0].title == "call"
            assert app.todos[0].notes == "portare doc"

    asyncio.run(t())


def test_form_anteprima_live(tmp_files):
    """Digitare aggiorna la preview senza compilare i campi."""

    async def t():
        app = make_app([])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_new_todo()
            await pilot.pause()
            await pilot.pause()
            scr = app.screen
            scr.query_one("#title-input", Input).value = "call domani #casa"
            await pilot.pause()
            preview = str(scr.query_one("#nl-preview", Label).render())
            assert "#casa" in preview
            assert scr.query_one("#due-input", Input).value == ""  # non compilato
            scr.query_one("#title-input", Input).value = "Solo titolo"
            await pilot.pause()
            from carpediem.lang import T as _T

            assert _T("nl_hint") in str(scr.query_one("#nl-preview", Label).render())

    asyncio.run(t())


def test_form_ctrl_l_nessun_campo(tmp_files):
    async def t():
        app = make_app([])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_new_todo()
            await pilot.pause()
            await pilot.pause()
            app.screen.query_one("#title-input", Input).value = "Solo titolo"
            await pilot.press("ctrl+l")
            await pilot.pause()
            scr = app.screen
            assert scr.query_one("#title-input", Input).value == "Solo titolo"
            assert scr.query_one("#due-input", Input).value == ""

    asyncio.run(t())


def _nl_example_of_day():
    from datetime import date as _date

    from carpediem.lang import T as _T

    examples = [_T("nl_exa1"), _T("nl_exa2"), _T("nl_exa3")]
    return examples[_date.today().toordinal() % len(examples)]


def test_inserisci_esempio(tmp_files):
    """Click sul link a titolo vuoto: inserisce l'esempio, campi intatti."""

    async def t():
        app = make_app([])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_new_todo()
            await pilot.pause()
            await pilot.pause()
            scr = app.screen
            await pilot.click(scr.query_one("#nl-try", Label))
            await pilot.pause()
            assert scr.query_one("#title-input", Input).value == _nl_example_of_day()
            assert scr.query_one("#due-input", Input).value == ""
            preview = str(scr.query_one("#nl-preview", Label).render())
            assert "→" in preview  # live preview ha parsato l'esempio

    asyncio.run(t())


def test_inserisci_esempio_titolo_pieno(tmp_files):
    """A titolo pieno il link non distrugge niente."""

    async def t():
        app = make_app([])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_new_todo()
            await pilot.pause()
            await pilot.pause()
            scr = app.screen
            scr.query_one("#title-input", Input).value = "mio testo"
            await pilot.click(scr.query_one("#nl-try", Label))
            await pilot.pause()
            assert scr.query_one("#title-input", Input).value == "mio testo"

    asyncio.run(t())


def test_placeholder_rotante(tmp_files):
    async def t():
        from carpediem.lang import T as _T

        app = make_app([])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_new_todo()
            await pilot.pause()
            await pilot.pause()
            ph = app.screen.query_one("#title-input", Input).placeholder
            assert ph == _T("form_title_ph", ex=_nl_example_of_day())

    asyncio.run(t())


def test_striscia_non_troncata(tmp_files):
    """La striscia sintassi va a capo (width 1fr), niente clipping orizzontale."""

    async def t():
        app = make_app([])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_new_todo()
            await pilot.pause()
            await pilot.pause()
            w = app.screen.query_one("#nl-syntax", Label)
            assert w.region.height >= 2
            assert w.scrollable_content_region.width <= w.region.width

    asyncio.run(t())


def _cli(args, home):
    root = _P(__file__).resolve().parent.parent
    env = dict(
        os.environ,
        TASKO_HOME=str(home),
        PYTHONPATH=str(root / "src") + os.pathsep + os.environ.get("PYTHONPATH", ""),
    )
    return subprocess.run(
        [sys.executable, "-m", "carpediem.main", *args],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_cli_add_nl(tmp_path):
    home = tmp_path / "home"
    r = _cli(["add", PHRASE], home=home)
    assert r.returncode == 0, r.stderr
    tid = int(r.stdout.strip())
    r = _cli(["list", "--porcelain"], home=home)
    assert r.returncode == 0
    assert f"{tid}|attivo|alta|2026-12-01 09:30|Report" in r.stdout, r.stdout
    r = _cli(["show", str(tid)], home=home)
    assert "lavoro" in r.stdout and "ufficio" in r.stdout


def test_cli_add_classico_invariato(tmp_path):
    home = tmp_path / "home"
    # flag espliciti = titolo alla lettera, zero parsing NL
    r = _cli(["add", "Report domani", "--project", "x"], home=home)
    assert r.returncode == 0, r.stderr
    tid = int(r.stdout.strip())
    r = _cli(["list", "--porcelain"], home=home)
    assert f"{tid}|attivo|media|-|Report domani" in r.stdout, r.stdout


def test_cli_add_titolo_vuoto(tmp_path):
    home = tmp_path / "home"
    r = _cli(["add", ""], home=home)
    assert r.returncode == 2
    r = _cli(["add", "   "], home=home)
    assert r.returncode == 2
    r = _cli(["list", "--porcelain"], home=home)
    assert r.stdout.strip() == ""
