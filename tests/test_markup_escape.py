"""Markup Rich nel testo utente: quadre escapate, mai MarkupError."""

from rich.markup import render

from src.screens._shared import _escape_markup
from tests.conftest import make_app, make_todo, run, screen_texts

EVIL = "Report [/] crash"
EVIL2 = "Nota [red] finta"


def test_escape_rende_letterali_e_non_sollevano():
    for raw in (EVIL, EVIL2, "chiudi [/b] fine", "tag [x] qui"):
        esc = _escape_markup(raw)
        assert render(esc).plain == raw  # a video il testo e' identico


def test_home_e_dettaglio_con_titoli_maligni(tmp_files):
    """Prima del fix: MarkupError all'apertura del dettaglio."""

    async def t():
        app = make_app(
            [
                make_todo(EVIL, todo_id=1, project="pr[/]og", tags=["a[/]b"]),
                make_todo(EVIL2, todo_id=2, notes="nota [/] lunga " * 5),
            ]
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.pause()
            home = screen_texts(app.screen)
            assert _escape_markup(EVIL) in home  # mini-kanban: sorgente escapata
            app.action_view_detail()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "DetailScreen"
            detail = screen_texts(app.screen)
            assert _escape_markup(EVIL2) in detail
            assert _escape_markup("nota [/] lunga") in detail

    run(t())


def test_agenda_e_settimana_con_titoli_maligni(tmp_files):
    async def t():
        from datetime import datetime

        from src.models import Priority

        today = datetime.now().strftime("%Y-%m-%d")
        app = make_app(
            [
                make_todo(EVIL, todo_id=1, due=today),
                make_todo(EVIL2, todo_id=2, priority=Priority.HIGH),
            ]
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_view_agenda()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "AgendaScreen"
            assert _escape_markup(EVIL) in screen_texts(app.screen)
            await pilot.press("escape")
            await pilot.pause()
            app.action_view_week()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "WeekScreen"
            assert _escape_markup(EVIL) in screen_texts(app.screen)

    run(t())


def test_toast_e_barra_con_testo_maligno(tmp_files):
    async def t():
        app = make_app([make_todo(EVIL, todo_id=1, tags=["a[/]b"])])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_filter_by_tag()  # toast n_ftag con tag maligno
            await pilot.pause()
            await pilot.pause()
            assert _escape_markup("a[/]b") in screen_texts(app.screen)
            app.filter_search = EVIL
            app._populate_table()  # stats-bar con ricerca maligna
            await pilot.pause()
            assert _escape_markup(EVIL) in screen_texts(app.screen)

    run(t())
