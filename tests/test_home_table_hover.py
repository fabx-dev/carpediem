"""Hover/highlight e primo paint del DataTable in home.

Regressioni legate al mouse e al radar:
- un click su area vuota non deve lasciare una riga evidenziata come hover
  (prima: _set_hover_cursor(True) era chiamato incondizionatamente, e il
  delegate a super la riattivava di nuovo).
- il click su una riga valida continua ad aprire il dettaglio.
- le dimensioni della tabella sono finali gia' al primo frame: con il radar
  attivo il message pump e' occupato e l'idle arriva dopo il paint, lasciando
  le colonne compatte finche' un evento (mouse/cambio tab) non ridipinge.
"""

from src.lang import T
from tests.conftest import make_app, make_todo, run


class _Event:
    """Evento click minimale: solo style.meta e stop()."""

    def __init__(self, meta):
        self.style = type("_Style", (), {"meta": meta})()
        self.stopped = False

    def stop(self):
        self.stopped = True


def test_click_su_area_vuota_spegne_hover(tmp_files):
    """Click su area grigia: nessuna riga resta evidenziata, nessun dettaglio."""

    async def t():
        app = make_app(
            [
                make_todo("A", todo_id=1, notes="nota uno"),
                make_todo("B", todo_id=2, notes="nota due"),
            ]
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            table = app.query_one("#todo-table")
            # Simula un click su area vuota (meta senza riga): l'hover cursor
            # resta acceso solo se il fix non funziona.
            table._show_hover_cursor = True
            await table._on_click(_Event({}))
            await pilot.pause()
            assert table._show_hover_cursor is False
            assert type(app.screen).__name__ != "DetailScreen"

    run(t())


def test_click_su_riga_apre_dettaglio(tmp_files):
    """Click su una riga valida apre il dettaglio (regressione: non rompere)."""

    async def t():
        app = make_app([make_todo("A", todo_id=1, notes="nota uno")])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            table = app.query_one("#todo-table")
            await table._on_click(_Event({"row": 0, "column": 1}))
            await pilot.pause()
            await pilot.pause()
            assert table._show_hover_cursor is True
            assert type(app.screen).__name__ == "DetailScreen"

    run(t())


def test_dimensioni_tabella_finali_al_primo_frame(tmp_files):
    """Le larghezze colonna sono calcolate prima di qualunque idle.

    Prima del fix: con il radar attivo il primo paint usciva con le colonne
    compatte (dimensioni provvisorie) e restava tale finche' un evento non
    forzava il repaint. Il calcolo sincrono in _populate_table lo evita."""

    async def t():
        app = make_app(
            [
                make_todo(
                    "Titolo molto lungo da riempire",
                    todo_id=i,
                    notes="Nota con testo abbastanza lungo",
                )
                for i in (1, 2, 3)
            ]
        )
        async with app.run_test(size=(120, 40)) as pilot:
            # NESSUNA pause: il calcolo deve essere gia' avvenuto in on_mount
            table = app.query_one("#todo-table")
            assert not table._require_update_dimensions
            widths = [c.content_width for c in table.columns.values()]
            assert widths[2] > 10, f"colonna Titolo compatta: {widths}"
            assert widths[5] > 10, f"colonna Note compatta: {widths}"
            assert table.virtual_size.width > 0
            # idempotente: nessun cambio dopo l'idle
            await pilot.pause()
            assert [c.content_width for c in table.columns.values()] == widths

    run(t())


def test_populate_con_tabella_vuota_non_crasha(tmp_files):
    """Il calcolo sincrono regge anche senza righe (ramo table_empty)."""

    async def t():
        app = make_app([])
        async with app.run_test(size=(120, 40)) as pilot:
            table = app.query_one("#todo-table")
            assert not table._require_update_dimensions
            assert table.row_count == 1  # riga "table_empty"
            await pilot.pause()
            assert T("table_empty") in [table.get_cell_at((0, 2))]

    run(t())
