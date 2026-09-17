"""Calendario picker nel form: apertura, selezione, orario preservato, layout."""

from datetime import datetime, timedelta

from textual.widgets import Input

from tests.conftest import make_app, run


def _ds(offset: int) -> str:
    return (datetime.now().date() + timedelta(days=offset)).strftime("%Y-%m-%d")


def test_picker_apre_e_seleziona_giorno(tmp_files):
    async def t():
        app = make_app([])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_new_todo()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "TodoFormScreen"
            await pilot.click("#due-cal-btn")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "CalendarPickScreen"
            # Seleziona il giorno 15 del mese corrente (esiste sempre).
            await pilot.click("#calpick-day-15")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "TodoFormScreen"
            today = datetime.now()
            expected = f"{today.year:04d}-{today.month:02d}-15"
            assert app.screen.query_one("#due-input", Input).value == expected

    run(t())


def test_picker_preserva_orario(tmp_files):
    async def t():
        app = make_app([])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_new_todo()
            await pilot.pause()
            await pilot.pause()
            app.screen.query_one("#due-input", Input).value = "2026-12-01 09:30"
            await pilot.click("#due-cal-btn")
            await pilot.pause()
            await pilot.pause()
            await pilot.click("#calpick-day-20")
            await pilot.pause()
            await pilot.pause()
            assert app.screen.query_one("#due-input", Input).value == "2026-12-20 09:30"

    run(t())


def test_picker_esc_non_modifica(tmp_files):
    async def t():
        app = make_app([])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_new_todo()
            await pilot.pause()
            await pilot.pause()
            app.screen.query_one("#due-input", Input).value = "2026-12-01 09:30"
            await pilot.click("#due-cal-btn")
            await pilot.pause()
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "TodoFormScreen"
            assert app.screen.query_one("#due-input", Input).value == "2026-12-01 09:30"

    run(t())


def test_picker_cambio_mese_e_oggi(tmp_files):
    async def t():
        app = make_app([])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_new_todo()
            await pilot.pause()
            await pilot.pause()
            await pilot.click("#due-cal-btn")
            await pilot.pause()
            await pilot.pause()
            # Cambia mese in avanti: il giorno 1 del mese successivo.
            await pilot.click("#calpick-next")
            await pilot.pause()
            await pilot.pause()
            today = datetime.now()
            nxt_year, nxt_month = today.year, today.month
            nxt_month += 1
            if nxt_month > 12:
                nxt_month = 1
                nxt_year += 1
            await pilot.click("#calpick-day-1")
            await pilot.pause()
            await pilot.pause()
            expected = f"{nxt_year:04d}-{nxt_month:02d}-01"
            assert app.screen.query_one("#due-input", Input).value == expected

    run(t())


def test_picker_tastiera_frecce(tmp_files):
    async def t():
        app = make_app([])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_new_todo()
            await pilot.pause()
            await pilot.pause()
            await pilot.click("#due-cal-btn")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "CalendarPickScreen"
            # Enter seleziona il giorno in focus (iniziale = oggi).
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "TodoFormScreen"
            assert app.screen.query_one("#due-input", Input).value == _ds(0)

    run(t())


def test_picker_layout_terminale_piccolo(tmp_files):
    from src.screens.form import CalendarPickScreen

    async def t():
        for size in ((120, 40), (80, 24), (70, 20)):
            app = make_app([])
            async with app.run_test(size=size) as pilot:
                await pilot.pause()
                app.push_screen(CalendarPickScreen(initial="2026-12-01"))
                await pilot.pause()
                await pilot.pause()
                assert type(app.screen).__name__ == "CalendarPickScreen"
                box = app.screen.query_one("#calpick-box").region
                close = app.screen.query_one("#calpick-close").region
                assert close.y >= box.y, (size, close, box)
                assert close.y + close.height <= box.y + box.height, (
                    size,
                    close,
                    box,
                )

    run(t())


def test_picker_giorni_visibili(tmp_files):
    """I numeri dei giorni devono rendere davvero (height:2 li collassava a 0)."""
    from src.screens.form import CalendarPickScreen

    async def t():
        app = make_app([])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.push_screen(CalendarPickScreen(initial="2026-12-01"))
            await pilot.pause()
            await pilot.pause()
            day = app.screen.query_one("#calpick-day-15")
            assert day.content_size.height > 0, day.content_size
            assert str(day.render()).strip() == "15"

    run(t())


def test_picker_box_centrato(tmp_files):
    from src.screens.form import CalendarPickScreen

    async def t():
        app = make_app([])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.push_screen(CalendarPickScreen(initial="2026-12-01"))
            await pilot.pause()
            await pilot.pause()
            box = app.screen.query_one("#calpick-box").region
            assert box.x == (120 - box.width) // 2
            assert box.y == (40 - box.height) // 2

    run(t())


def _cell_text(screen, bid):
    """Testo renderizzato alla dimensione reale di layout (non intrinseca).

    b.render() usa la larghezza di contenuto e non vede il troncamento:
    render_lines con la region reale sì (border/box consumano le colonne).
    """
    from textual.geometry import Region

    b = screen.query_one(f"#{bid}")
    lines = b.render_lines(Region(0, 0, b.region.width, b.region.height))
    return "".join(s.text for s in lines)


def test_picker_oggi_numero_intero(tmp_files):
    """La cella di oggi deve mostrare il numero per intero.

    Il bordo `thick` consumava le colonne della cella 1fr e "17" rendeva "1".
    """
    from src.screens.form import CalendarPickScreen

    today = datetime.now().date()

    async def t():
        app = make_app([])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.push_screen(CalendarPickScreen(initial=""))
            await pilot.pause()
            await pilot.pause()
            txt = _cell_text(app.screen, f"calpick-day-{today.day}")
            assert str(today.day) in txt, txt

    run(t())


def test_picker_selezionato_terminale_stretto(tmp_files):
    """Il giorno selezionato resta leggibile a terminale stretto.

    Con `border: thick` il contenuto collassava a 0 colonne e il renderer
    sollevava ValueError invece di mostrare il numero.
    """
    from src.screens.form import CalendarPickScreen

    async def t():
        app = make_app([])
        async with app.run_test(size=(40, 24)) as pilot:
            await pilot.pause()
            app.push_screen(CalendarPickScreen(initial="2026-09-15"))
            await pilot.pause()
            await pilot.pause()
            txt = _cell_text(app.screen, "calpick-day-15")
            assert "15" in txt, txt

    run(t())


def test_picker_bottone_icona(tmp_files):
    async def t():
        app = make_app([])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_new_todo()
            await pilot.pause()
            await pilot.pause()
            btn = app.screen.query_one("#due-cal-btn")
            assert btn.region.width <= 4, btn.region
            assert "📅" in str(btn.render())
            assert btn.tooltip

    run(t())
