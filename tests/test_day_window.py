"""day_window nel config: Buongiorno la scrive, piano giorno la consultabile.

Buongiorno decide cosa entra nel piano (planned_for) e, alla conferma,
scrive la finestra orari + eventi fissi strutturati. Il piano giorno
organizza temporalmente cio' che e' entrato nel piano: nessuna seconda
selezione, nessun default di orari.
"""

import asyncio
import json
from datetime import datetime, timedelta

from src.lang import T as _T
from src.models import Priority
from src.storage import _validate_day_window
from tests.conftest import make_app, make_todo, screen_texts


def _day(offset: int) -> str:
    return (datetime.now().date() + timedelta(days=offset)).strftime("%Y-%m-%d")


def _window(day: str, events=None) -> dict:
    return {
        "date": day,
        "start": "09:00",
        "end": "18:00",
        "events": events or [],
    }


def _todos(planned=True):
    pf = {"planned_for": _day(0)} if planned else {}
    return [
        make_todo("A-ritardo", todo_id=1, due=_day(-1), priority=Priority.HIGH, **pf),
        make_todo("B-oggi", todo_id=2, stima_pomo=2, **pf),
        make_todo("C-libero", todo_id=3, priority=Priority.LOW, **pf),
    ]


# --- storage: validazione tollerante --------------------------------------


def test_day_window_valida_e_canonica(tmp_files):
    v = _validate_day_window(
        {
            "date": _day(0),
            "start": "9:00",
            "end": "18:00",
            "events": [{"start": "13:00", "end": "14:00", "title": " Pranzo "}],
        }
    )
    assert v == {
        "date": _day(0),
        "start": "09:00",
        "end": "18:00",
        "events": [{"start": "13:00", "end": "14:00", "title": "Pranzo"}],
    }


def test_day_window_invalida_scartata_mai_crash(tmp_files):
    buone = {"date": _day(0), "start": "09:00", "end": "18:00"}
    for bad in (
        None,
        [],
        "x",
        42,
        {},
        {"date": "21-09-2026", "start": "09:00", "end": "18:00"},
        {"date": "2026-13-40", "start": "09:00", "end": "18:00"},
        {**buone, "start": ""},
        {**buone, "end": None},
        {**buone, "start": "18:00", "end": "09:00"},
        {**buone, "start": "09:00", "end": "09:00"},
    ):
        assert _validate_day_window(bad) is None, bad


def test_day_window_eventi_scartati_cap_e_troncamento(tmp_files):
    evs = [
        {"start": "13:00", "end": "14:00", "title": "Ok"},
        {"start": "14:00", "end": "13:00", "title": "Invertito"},
        {"start": "xx", "end": "15:00", "title": "Brutto"},
        "stringa-pura",
        {"start": "15:00", "end": "16:00", "title": "x" * 300},
    ]
    v = _validate_day_window(
        {"date": _day(0), "start": "08:00", "end": "20:00", "events": evs}
    )
    assert [e["title"] for e in v["events"]] == ["Ok", "x" * 120]
    many = [{"start": "10:00", "end": "10:30", "title": "e"}] * 35
    v2 = _validate_day_window(
        {"date": _day(0), "start": "08:00", "end": "20:00", "events": many}
    )
    assert len(v2["events"]) == 30  # cap: mai config spropositata


def test_day_window_roundtrip_whitelist(tmp_files):
    import src.storage as s

    w = _window(_day(0), [{"start": "13:00", "end": "14:00", "title": "Pranzo"}])
    s.save_config({**s.load_config(), "day_window": w})
    assert s.load_config()["day_window"] == w
    # file vecchio senza chiave -> None
    s.CONFIG_FILE.write_text(json.dumps({"theme": "matrix"}), encoding="utf-8")
    assert s.load_config()["day_window"] is None
    # chiave brutta su disco -> None al load (mai crash)
    s.CONFIG_FILE.write_text(
        json.dumps({"day_window": {"date": "nope"}}), encoding="utf-8"
    )
    assert s.load_config()["day_window"] is None


# --- Buongiorno: conferma scrive, Esc non scrive ---------------------------


async def _open_buongiorno(pilot, app):
    await pilot.press("P")
    await pilot.pause()
    await pilot.pause()
    assert type(app.screen).__name__ == "PlanProposalScreen"


async def _set_times(pilot, screen, start=None, end=None):
    from textual.widgets import Input

    if start is not None:
        screen.query_one("#planp-start", Input).value = start
    if end is not None:
        screen.query_one("#planp-end", Input).value = end
    await pilot.pause()
    await pilot.pause()


async def _set_events(pilot, screen, text):
    from textual.widgets import TextArea

    area = screen.query_one("#planp-events", TextArea)
    area.text = text
    area.post_message(TextArea.Changed(area))
    await pilot.pause()
    await pilot.pause()


def test_buongiorno_conferma_scrive_finestra_strutturata(tmp_files):
    async def t():
        app = make_app(_todos())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_buongiorno(pilot, app)
            await _set_times(pilot, app.screen, start="09:00", end="18:00")
            await _set_events(pilot, app.screen, "13:00-14:00 Pranzo")
            await pilot.press("s")
            await pilot.pause()
            await pilot.pause()
            expected = _window(
                _day(0), [{"start": "13:00", "end": "14:00", "title": "Pranzo"}]
            )
            assert app.config["day_window"] == expected
            import src.storage as s

            assert s.load_config()["day_window"] == expected

    asyncio.run(t())


def test_buongiorno_esc_non_scrive_finestra(tmp_files):
    async def t():
        app = make_app(_todos())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_buongiorno(pilot, app)
            await _set_times(pilot, app.screen, start="09:00", end="18:00")
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()
            assert app.config.get("day_window") is None
            assert "09:00–09:30" not in screen_texts(app.screen)

    asyncio.run(t())


def test_buongiorno_senza_orari_cancella_stale(tmp_files):
    async def t():
        app = make_app(_todos())
        app.config["day_window"] = _window(_day(-1))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_buongiorno(pilot, app)
            await pilot.press("s")
            await pilot.pause()
            await pilot.pause()
            assert app.config.get("day_window") is None

    asyncio.run(t())


def test_buongiorno_finestra_invalida_cancella_stale(tmp_files):
    async def t():
        app = make_app(_todos())
        app.config["day_window"] = _window(_day(0))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_buongiorno(pilot, app)
            await _set_times(pilot, app.screen, start="09:00", end="08:00")
            await pilot.press("s")
            await pilot.pause()
            await pilot.pause()
            assert app.config.get("day_window") is None

    asyncio.run(t())


# --- Piano giorno: timeline della scheda operativa --------------------------


async def _open_plan(pilot, app):
    app.action_view_daily_plan()
    await pilot.pause()
    await pilot.pause()
    assert type(app.screen).__name__ == "DailyPlanScreen"


def test_piano_senza_finestra_solo_task(tmp_files):
    """Degradazione pattuita: nessun orario -> piano come sempre, zero timeline."""

    async def t():
        app = make_app(_todos())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            txt = screen_texts(app.screen)
            assert _T("plan_sec_planned", win="", load="")[:20] in txt or (
                "A-ritardo" in txt
            )
            assert _T("plan_sec_window", window="09:00–18:00") not in txt
            assert _T("planp_event_tag") not in txt
            assert "09:00–" not in txt

    asyncio.run(t())


def test_piano_finestra_stale_ignorata(tmp_files):
    async def t():
        app = make_app(_todos())
        app.config["day_window"] = _window(_day(-1))  # ieri
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            assert "09:00–09:30" not in screen_texts(app.screen)

    asyncio.run(t())


def test_piano_timeline_task_confermati(tmp_files):
    """Esattamente i confermati, organizzati temporalmente: ordine di merito
    dal Planner, ma nessuna riproposta (tutti i planned_for hanno uno slot
    o restano in coda senza orario, sempre operativi)."""

    async def t():
        app = make_app(_todos(planned=True))
        app.config["day_window"] = _window(_day(0))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            txt = screen_texts(app.screen)
            # Timeline nell'header della sezione pianificati.
            assert _T("plan_sec_window", window="09:00–18:00") in txt
            assert "09:00–09:30 A-ritardo" in txt
            assert "09:30–10:30 B-oggi" in txt
            assert "10:30–11:00 C-libero" in txt
            # Nessuna riproposta: i confermati oltre capacita' restano in
            # coda come righe operative SENZA prefisso orario (niente
            # riga-riassunto "Senza orario: ...").
            app2 = make_app(_todos(planned=True))
            app2.config["day_window"] = {
                "date": _day(0),
                "start": "09:00",
                "end": "09:30",
                "events": [],
            }
            app2.action_view_daily_plan()
            await pilot.pause()
            await pilot.pause()
            txt2 = screen_texts(app2.screen)
            assert "09:00–09:30 A-ritardo" in txt2
            assert _T("planp_slots_un", t="") not in txt2  # niente riassunto
            assert "B-oggi" in txt2 and "C-libero" in txt2
            assert "09:00–09:30 B-oggi" not in txt2  # senza slot, senza orario

    asyncio.run(t())


def test_piano_timeline_eventi_fissi(tmp_files):
    async def t():
        app = make_app(_todos(planned=True))
        app.config["day_window"] = _window(
            _day(0), [{"start": "13:00", "end": "14:00", "title": "Pranzo"}]
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            txt = screen_texts(app.screen)
            assert "13:00–14:00 EVENTO: Pranzo" in txt
            # Nessuno slot tocca l'evento (busy hard constraint).
            assert "13:00–13:30" not in txt and "13:30–14:00" not in txt

    asyncio.run(t())


def test_piano_timeline_solo_task_confermati(tmp_files):
    """Task NON confermati (solo scadenza, non in piano) fuori dalla timeline:
    Buongiorno decide cosa entra, il piano giorno organizza solo quello."""

    async def t():
        app = make_app(_todos(planned=False))  # nessuno in piano
        app.config["day_window"] = _window(_day(0))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            txt = screen_texts(app.screen)
            assert _T("plan_sec_window", window="09:00–18:00") not in txt
            assert "09:00–09:30" not in txt

    asyncio.run(t())


def _label_text(c) -> str:
    """Testo della prima Label della riga (compatibile Textual 3.x/8.x)."""
    labels = c.query("Label")
    if not labels:
        return ""
    w = labels.first()
    content = getattr(w, "content", None)
    if content is None:
        content = getattr(w, "renderable", "")
    return str(content)


def test_piano_righe_timed_operative(tmp_files):
    """Le righe con orario sono PlanRow operative: _cur le identifica come
    (task_id, "planned") e Enter apre il dettaglio dalla riga timed."""
    from textual.widgets import ListView

    from src.screens.plan import PlanRow

    async def t():
        app = make_app(_todos(planned=True))
        app.config["day_window"] = _window(_day(0))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            lv = app.screen.query_one("#plan-section", ListView)
            # Le righe timed della sezione planned sono PlanRow con task_id.
            timed = [
                c
                for c in lv.children
                if isinstance(c, PlanRow)
                and c.section == "planned"
                and "–" in _label_text(c)
            ]
            assert len(timed) == 3  # tutti e tre confermati con slot
            # Highlight sulla prima riga timed: identificata correttamente.
            first = timed[0]
            lv.index = list(lv.children).index(first)
            await pilot.pause()
            item = lv.highlighted_child
            assert getattr(item, "task_id", None) == 1
            assert getattr(item, "section", None) == "planned"
            # Enter dalla riga timed apre il dettaglio.
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "DetailScreen"
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()

    asyncio.run(t())


def test_piano_riga_timed_x_rimuove(tmp_files):
    """x su una riga con orario la rimuove dal piano (operativita' piena)."""
    from textual.widgets import ListView

    from src.screens.plan import PlanRow

    async def t():
        app = make_app(_todos(planned=True))
        app.config["day_window"] = _window(_day(0))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            lv = app.screen.query_one("#plan-section", ListView)
            timed = [
                c
                for c in lv.children
                if isinstance(c, PlanRow) and c.section == "planned"
            ]
            first = timed[0]
            lv.index = list(lv.children).index(first)
            await pilot.pause()
            await pilot.press("x")
            await pilot.pause()
            await pilot.pause()
            by_id = {t.id: t for t in app.todos}
            assert by_id[first.task_id].planned_for != _day(0)

    asyncio.run(t())


def test_piano_eventi_disabled_e_task_operativi(tmp_files):
    """Gli eventi fissi sono righe disabled informative; i task (con e senza
    slot) restano righe abilitate."""
    from textual.widgets import ListItem, ListView

    from src.screens.plan import PlanRow

    async def t():
        app = make_app(_todos(planned=True))
        app.config["day_window"] = _window(
            _day(0), [{"start": "13:00", "end": "14:00", "title": "Pranzo"}]
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            lv = app.screen.query_one("#plan-section", ListView)

            def row_text(c):
                return _label_text(c)

            n_events = 0
            for c in lv.children:
                if "EVENTO:" in row_text(c):
                    n_events += 1
                    # Riga evento: ListItem (non PlanRow) disabled.
                    assert isinstance(c, ListItem) and not isinstance(c, PlanRow)
                    assert c.disabled
                elif isinstance(c, PlanRow) and c.section == "planned":
                    # Task pianificati (con o senza slot): sempre operativi.
                    assert not c.disabled
            assert n_events == 1

    asyncio.run(t())


def test_piano_timeline_layout_piccolo(tmp_files):
    """A taglie piccole la timeline scorre nella lista: cornice e Chiudi
    restano dentro il box (nessuna compressione fuori schema)."""

    async def t():
        for size in ((120, 40), (80, 24), (70, 20)):
            app = make_app(_todos(planned=True))
            app.config["day_window"] = _window(_day(0))
            async with app.run_test(size=size) as pilot:
                await pilot.pause()
                await _open_plan(pilot, app)
                from textual.widgets import Button

                box = app.screen.query_one("#plan-box").region
                close = app.screen.query_one("#plan-close", Button).region
                assert close.y + close.height <= box.y + box.height, size
                assert close.x + close.width <= box.x + box.width, size

    asyncio.run(t())
