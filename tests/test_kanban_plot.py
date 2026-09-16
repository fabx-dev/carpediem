"""Test radar scadenze: helper puri + pilot home (file isolati da conftest)."""

from datetime import datetime, timedelta

import pytest
from textual.widgets import Button

import src.app as app_module
from src.domain import RADAR_CAP, kanban_plot_data, radar_hit
from src.lang import T
from src.models import Priority
from tests.conftest import make_app, make_todo, run, screen_texts, wait_for

TODAY = "2026-09-16"


def test_vuoto():
    d = kanban_plot_data([], TODAY)
    assert d["points"] == []
    assert (d["late"], d["open_ok"], d["closed7"], d["nodate"]) == (0, 0, 0, 0)
    assert d["worst"] == []


def test_misto():
    todos = [
        make_todo("ritardo-alta", todo_id=1, due="2026-09-07", priority=Priority.HIGH),
        make_todo("ritardo-bassa", todo_id=2, due="2026-09-15", priority=Priority.LOW),
        make_todo("futuro", todo_id=3, due="2026-09-20", priority=Priority.MEDIUM),
        make_todo("senza-data", todo_id=4, priority=Priority.HIGH),
        make_todo("chiuso-ieri", todo_id=5, done=True, completed_at="2026-09-15 10:00"),
        make_todo(
            "chiuso-vecchio", todo_id=6, done=True, completed_at="2026-08-01 10:00"
        ),
        make_todo("sub", todo_id=7, due="2026-09-01", parent_id=1),
        make_todo("sospeso", todo_id=8, due="2026-09-10", paused=True),
    ]
    d = kanban_plot_data(todos, TODAY)
    by_id = {p[0]: p for p in d["points"]}
    assert set(by_id) == {1, 2, 3, 8}
    assert by_id[1][1] == -9 and by_id[1][3] == "late"
    assert by_id[3][1] == 4 and by_id[3][3] == "open"
    assert d["late"] == 3 and d["open_ok"] == 1
    assert d["closed7"] == 1 and d["nodate"] == 1
    assert d["worst"] == [(1, -9), (8, -6)]
    # fascia y per priorita' (modulo jitter deterministico)
    assert 2.75 <= by_id[1][2] <= 3.25
    assert 0.75 <= by_id[2][2] <= 1.25


def test_cap_e_due_invalida():
    todos = [
        make_todo("lontano", todo_id=1, due="2027-01-01"),
        make_todo("rotta", todo_id=2, due="31/02/2026"),
    ]
    d = kanban_plot_data(todos, TODAY)
    by_id = {p[0]: p for p in d["points"]}
    assert by_id[1][1] == RADAR_CAP
    assert 2 not in by_id and d["nodate"] == 1


def test_id_none_e_done_senza_data_esclusi():
    todos = [
        make_todo("noid", todo_id=None, due="2026-09-10"),
        make_todo("chiuso-senza-data", todo_id=2, done=True),
        make_todo("ok", todo_id=3, due="2026-09-10"),
    ]
    d = kanban_plot_data(todos, TODAY)  # senza TypeError su id misti
    assert {p[0] for p in d["points"]} == {3}
    assert d["closed7"] == 0


def test_today_invalida():
    with pytest.raises(ValueError):
        kanban_plot_data([], "xx")


def test_hash_cambia_con_mutazione():
    t = make_todo("a", todo_id=1, due="2026-09-20")
    h1 = kanban_plot_data([t], TODAY)["phash"]
    assert kanban_plot_data([t], TODAY)["phash"] == h1
    t2 = make_todo("a", todo_id=1, due="2026-09-21")
    assert kanban_plot_data([t2], TODAY)["phash"] != h1


def test_hit():
    pts = [(12, -9.0, 3.1, "late"), (15, -9.0, 2.9, "late"), (18, 5.0, 1.0, "open")]
    assert radar_hit(pts, -9.0, 3.0) == [12, 15]
    assert radar_hit(pts, 5.0, 1.0) == [18]
    assert radar_hit(pts, 0.0, 2.0) == []


def test_geometria_plot_stabile(tmp_files, monkeypatch):
    """Golden test (S0): se plotext sposta il layout, qui si rompe forte."""
    plt_mod = pytest.importorskip("textual_plotext.plot")
    import re

    def canvas(width, pts):
        monkeypatch.setenv("COLUMNS", str(width))
        p = plt_mod.Plot()
        app_module.TodoApp._draw_radar(
            None, p, {"points": pts, "worst": [], "late": 0, "open_ok": 0}
        )
        p.plotsize(width, 5)
        rows = re.sub(r"\x1b\[[0-9;]*m", "", p.build()).split("\n")
        return rows

    rows = canvas(80, [(7, -14, 2.0, "open")])
    assert [c for c, ch in enumerate(rows[1]) if ch in "▗▖▝▘"] == [3]
    rows = canvas(80, [(7, 14, 2.0, "open")])
    assert [c for c, ch in enumerate(rows[1]) if ch in "▗▖▝▘"] == [77]
    rows = canvas(80, [(7, 5, 2.0, "open")])
    assert [c for c, ch in enumerate(rows[0]) if ch == "│"] == [40]
    rows = canvas(80, [(7, 5, 3.2, "open")])
    assert [c for c, ch in enumerate(rows[0]) if ch in "▗▖▝▘"] == [53]
    rows = canvas(80, [(7, 5, 1.0, "open")])
    assert [c for c, ch in enumerate(rows[3]) if ch in "▗▖▝▘"] == [53]
    # formula inversa coerente entro mezza cella
    assert abs(app_module._radar_day(3, 80) - (-14)) < 0.6
    assert abs(app_module._radar_day(77, 80) - 14) < 0.6
    assert abs(app_module._radar_day(40, 80)) < 0.6


def test_geometria_plot_120(tmp_files, monkeypatch):
    plt_mod = pytest.importorskip("textual_plotext.plot")
    import re

    monkeypatch.setenv("COLUMNS", "120")
    p = plt_mod.Plot()
    app_module.TodoApp._draw_radar(
        None, p, {"points": [(7, 5, 2.0, "open")], "worst": []}
    )
    p.plotsize(120, 5)
    rows = re.sub(r"\x1b\[[0-9;]*m", "", p.build()).split("\n")
    assert len(rows[0]) == 120
    assert [c for c, ch in enumerate(rows[0]) if ch == "│"] == [60]


def _iso(days: int) -> str:
    return (datetime.now().date() + timedelta(days=days)).strftime("%Y-%m-%d")


def _radar_todos():
    return [
        make_todo("ritardo", todo_id=1, due=_iso(-9), priority=Priority.HIGH),
        make_todo("aperto", todo_id=2, due=_iso(5), priority=Priority.MEDIUM),
        make_todo("bassa", todo_id=3, due=_iso(-2), priority=Priority.LOW),
    ]


def test_mode_senza_dep_ricade_testo(tmp_files, monkeypatch):
    monkeypatch.setattr(app_module, "PlotextPlot", None)
    app = make_app(_radar_todos())
    assert app._kanban_mode() == "testo"
    app.config["kanban_mode"] = "grafico"
    assert app._kanban_mode() == "testo"


def test_grafico_senza_dati_ricade_testo(tmp_files):
    pytest.importorskip("textual_plotext")

    async def t():
        app = make_app([make_todo("senza-data", todo_id=1)])
        async with app.run_test(size=(80, 24)) as pilot:
            await wait_for(pilot, lambda: app._kb_auto_text)
            # Fallback transitorio: la preferenza resta grafico.
            assert app._kanban_mode() == "grafico"
            assert app.config["kanban_mode"] == "grafico"
            bar = app.query_one("#kanban-bar")
            assert not bar.has_class("hidden")

    run(t())


def test_plot_widget_e_caption(tmp_files):
    pytest.importorskip("textual_plotext")

    async def t():
        app = make_app(_radar_todos())
        async with app.run_test(size=(80, 24)) as pilot:
            await wait_for(
                pilot,
                lambda: not app.query_one("#kanban-plot").has_class("hidden"),
            )
            assert app._kanban_mode() == "grafico"
            texts = screen_texts(app)
            assert T("radar_title") in texts
            cap = T(
                "radar_cap",
                late=2,
                ok=1,
                worst=T("radar_worst_one", id=1, h=-9)
                + " "
                + T("radar_worst_one", id=3, h=-2),
            )
            assert cap in texts

    run(t())


def _click_col(app, horizon: float) -> tuple[int, int]:
    plot = app.query_one("#kanban-plot")
    w = plot.region.width
    span = app_module._radar_span(w)
    return round(w // 2 + horizon * span / 28), 0


def test_click_apre_dettaglio(tmp_files, monkeypatch):
    pytest.importorskip("textual_plotext")
    monkeypatch.setenv("COLUMNS", "80")

    async def t():
        app = make_app(_radar_todos())
        async with app.run_test(size=(80, 24)) as pilot:
            await wait_for(
                pilot,
                lambda: (
                    app._kanban_mode() == "grafico" and app._last_plot_hash is not None
                ),
            )
            col, row = _click_col(app, -9)
            await pilot.click("#kanban-plot", offset=(col, row))
            await wait_for(pilot, lambda: type(app.screen).__name__ == "DetailScreen")
            assert type(app.screen).__name__ == "DetailScreen"
            assert "ritardo" in screen_texts(app)

    run(t())


def test_click_vuoto_noop(tmp_files, monkeypatch):
    pytest.importorskip("textual_plotext")
    monkeypatch.setenv("COLUMNS", "80")

    async def t():
        app = make_app(_radar_todos())
        async with app.run_test(size=(80, 24)) as pilot:
            await wait_for(
                pilot,
                lambda: (
                    app._kanban_mode() == "grafico" and app._last_plot_hash is not None
                ),
            )
            n = len(app.screen_stack)
            await pilot.click("#kanban-plot", offset=(70, 4))
            await pilot.pause()
            await pilot.pause()
            assert len(app.screen_stack) == n
            assert type(app.screen).__name__ != "DetailScreen"

    run(t())


def test_click_multi_popup_e_scelta(tmp_files, monkeypatch):
    pytest.importorskip("textual_plotext")
    monkeypatch.setenv("COLUMNS", "80")

    async def t():
        todos = [
            make_todo("primo", todo_id=1, due=_iso(-9), priority=Priority.HIGH),
            make_todo("secondo", todo_id=2, due=_iso(-9), priority=Priority.HIGH),
            make_todo("altro", todo_id=3, due=_iso(6), priority=Priority.LOW),
        ]
        app = make_app(todos)
        async with app.run_test(size=(80, 24)) as pilot:
            await wait_for(
                pilot,
                lambda: (
                    app._kanban_mode() == "grafico" and app._last_plot_hash is not None
                ),
            )
            col, row = _click_col(app, -9)
            await pilot.click("#kanban-plot", offset=(col, row))
            await wait_for(
                pilot, lambda: type(app.screen).__name__ == "RadarPickScreen"
            )
            assert type(app.screen).__name__ == "RadarPickScreen"
            labels = [str(b.label) for b in app.screen.query(Button)]
            assert any("primo" in str(lb) for lb in labels)
            assert any("secondo" in str(lb) for lb in labels)
            await pilot.press("enter")
            await wait_for(pilot, lambda: type(app.screen).__name__ == "DetailScreen")
            assert type(app.screen).__name__ == "DetailScreen"

    run(t())


def test_doppio_click_un_solo_dettaglio(tmp_files, monkeypatch):
    pytest.importorskip("textual_plotext")
    monkeypatch.setenv("COLUMNS", "80")

    async def t():
        from types import SimpleNamespace

        app = make_app(_radar_todos())
        async with app.run_test(size=(80, 24)) as pilot:
            await wait_for(
                pilot,
                lambda: (
                    app._kanban_mode() == "grafico" and app._last_plot_hash is not None
                ),
            )
            col, row = _click_col(app, -9)
            rx, ry, _, _ = app.query_one("#kanban-plot").region
            ev = SimpleNamespace(screen_x=rx + col, screen_y=ry + row)
            # Due click nella stessa cella senza pause: il secondo trova
            # il modale e viene ignorato (mai due dettagli impilati).
            app.on_click(ev)
            app.on_click(ev)
            await wait_for(pilot, lambda: type(app.screen).__name__ == "DetailScreen")
            await pilot.pause()
            details = [
                s for s in app.screen_stack if type(s).__name__ == "DetailScreen"
            ]
            assert len(details) == 1

    run(t())


def test_doppio_enter_popup_un_solo_dettaglio(tmp_files, monkeypatch):
    pytest.importorskip("textual_plotext")
    monkeypatch.setenv("COLUMNS", "80")

    async def t():
        todos = [
            make_todo("primo", todo_id=1, due=_iso(-9), priority=Priority.HIGH),
            make_todo("secondo", todo_id=2, due=_iso(-9), priority=Priority.HIGH),
            make_todo("altro", todo_id=3, due=_iso(6), priority=Priority.LOW),
        ]
        app = make_app(todos)
        async with app.run_test(size=(80, 24)) as pilot:
            await wait_for(
                pilot,
                lambda: (
                    app._kanban_mode() == "grafico" and app._last_plot_hash is not None
                ),
            )
            col, row = _click_col(app, -9)
            await pilot.click("#kanban-plot", offset=(col, row))
            await wait_for(
                pilot, lambda: type(app.screen).__name__ == "RadarPickScreen"
            )
            pushed: list[str] = []
            orig_push = app.push_screen

            def spy(screen, *args, **kwargs):
                pushed.append(type(screen).__name__)
                return orig_push(screen, *args, **kwargs)

            app.push_screen = spy  # type: ignore[method-assign]
            await pilot.press("enter")
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            # Un solo dettaglio (il secondo Enter chiude il dettaglio:
            # comportamento preesistente della DetailScreen).
            assert pushed.count("DetailScreen") == 1

    run(t())


def test_popup_id_duplicati_senza_crash(tmp_files):
    from src.screens.form import RadarPickScreen

    async def t():
        app = make_app([])
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            app.push_screen(
                RadarPickScreen([(1, "a[/]x", -1), (1, "b", -2)]), lambda c: None
            )
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "RadarPickScreen"
            await pilot.press("escape")
            await wait_for(pilot, lambda: len(app.screen_stack) == 1)

    run(t())


def test_home_piccola_con_grafico(tmp_files, monkeypatch):
    pytest.importorskip("textual_plotext")
    monkeypatch.setenv("COLUMNS", "70")

    async def t():
        app = make_app(_radar_todos())
        async with app.run_test(size=(70, 20)) as pilot:
            await wait_for(
                pilot,
                lambda: (
                    app._kanban_mode() == "grafico" and app._last_plot_hash is not None
                ),
            )
            plot = app.query_one("#kanban-plot")
            assert plot.region.height == 5
            assert len(app._row_map) > 0
            texts = screen_texts(app)
            assert T("radar_title") in texts

    run(t())


def test_popup_esc_annulla(tmp_files, monkeypatch):
    pytest.importorskip("textual_plotext")
    monkeypatch.setenv("COLUMNS", "80")

    async def t():
        todos = [
            make_todo("primo", todo_id=1, due=_iso(-9), priority=Priority.HIGH),
            make_todo("secondo", todo_id=2, due=_iso(-9), priority=Priority.HIGH),
            make_todo("altro", todo_id=3, due=_iso(6), priority=Priority.LOW),
        ]
        app = make_app(todos)
        async with app.run_test(size=(80, 24)) as pilot:
            await wait_for(
                pilot,
                lambda: (
                    app._kanban_mode() == "grafico" and app._last_plot_hash is not None
                ),
            )
            col, row = _click_col(app, -9)
            await pilot.click("#kanban-plot", offset=(col, row))
            await wait_for(
                pilot, lambda: type(app.screen).__name__ == "RadarPickScreen"
            )
            await pilot.press("escape")
            await wait_for(pilot, lambda: len(app.screen_stack) == 1)
            assert len(app.screen_stack) == 1

    run(t())


def test_fallback_transitorio_e_auto_restore(tmp_files, monkeypatch):
    """DB senza punti: testo transitorio MAI persistito; ai punti torna il grafico."""
    pytest.importorskip("textual_plotext")
    monkeypatch.setenv("COLUMNS", "80")

    async def t():
        app = make_app([])
        async with app.run_test(size=(80, 24)) as pilot:
            await wait_for(pilot, lambda: app._kb_auto_text)
            # La preferenza resta grafico: nessun downgrade scritto in config.
            assert app._kanban_mode() == "grafico"
            assert app.config["kanban_mode"] == "grafico"
            assert app.query_one("#kanban-plot").has_class("hidden")
            # Aggiunta con scadenza: il grafico torna da solo, senza tasti.
            app.store.add(make_todo("nuovo", todo_id=1, due=_iso(-9)))
            app._populate_table()
            await wait_for(pilot, lambda: not app._kb_auto_text)
            assert app._kanban_mode() == "grafico"
            assert not app.query_one("#kanban-plot").has_class("hidden")
            assert "#1" in screen_texts(app)

    run(t())


def test_testo_esplicito_resta_testo(tmp_files, monkeypatch):
    """Scelta esplicita testo: le nuove scadenze non riaccendono il grafico."""
    pytest.importorskip("textual_plotext")
    monkeypatch.setenv("COLUMNS", "80")

    async def t():
        app = make_app([])
        async with app.run_test(size=(80, 24)) as pilot:
            await wait_for(pilot, lambda: app._kb_auto_text)
            app.action_toggle_kanban()  # grafico -> testo esplicito
            await pilot.pause()
            assert app.config["kanban_mode"] == "testo"
            assert not app._kb_auto_text
            app.store.add(make_todo("nuovo", todo_id=1, due=_iso(-9)))
            app._populate_table()
            await pilot.pause()
            await pilot.pause()
            assert app.config["kanban_mode"] == "testo"
            assert not app._kb_auto_text
            assert app.query_one("#kanban-plot").has_class("hidden")

    run(t())


def test_caption_mostra_senza_data():
    d = kanban_plot_data(
        [
            make_todo("nodate", todo_id=1),
            make_todo("futuro", todo_id=2, due="2026-09-20"),
        ],
        TODAY,
    )
    assert d["nodate"] == 1
    cap = app_module.TodoApp._radar_caption(None, d)
    assert T("radar_nodate", n=1) in cap
    d2 = kanban_plot_data([make_todo("futuro", todo_id=2, due="2026-09-20")], TODAY)
    assert T("radar_nodate", n=1) not in app_module.TodoApp._radar_caption(None, d2)
