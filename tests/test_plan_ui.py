"""Integrazione planner Sprint 4: tasto P, proposta, conferma, settings (isolati)."""

import asyncio
import json
from datetime import datetime, timedelta

from textual.widgets import Input, SelectionList

import src.main as m
from src.models import Priority
from tests.conftest import commands_module, make_app, make_todo, screen_texts


def _day(offset: int) -> str:
    return (datetime.now().date() + timedelta(days=offset)).strftime("%Y-%m-%d")


def _todos():
    return [
        make_todo("A-ritardo", todo_id=1, due=_day(-1), priority=Priority.HIGH),
        make_todo("B-oggi", todo_id=2, due=_day(0)),
        make_todo("C-libero", todo_id=3, priority=Priority.LOW),
        make_todo("D-fatto", todo_id=4, due=_day(-5), done=True),
    ]


def test_tasto_p_e_conferma(tmp_files):
    async def t():
        app = make_app(_todos())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("P")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "PlanProposalScreen"
            opts = app.screen.query_one("#planp-list", SelectionList)
            assert len(opts._options) == 3
            assert set(opts.selected) == {1, 2, 3}
            await pilot.press("ctrl+enter")
            await pilot.pause()
            await pilot.pause()
            today = _day(0)
            by_id = {t.id: t for t in app.todos}
            assert by_id[1].planned_for == today
            assert by_id[2].planned_for == today
            assert by_id[3].planned_for == today
            assert by_id[4].planned_for == ""

    asyncio.run(t())


def test_tagliati_non_preselezionati(tmp_files):
    async def t():
        app = make_app(_todos())
        app.config["day_hours"] = 0.5  # capacita' 1 pomo: solo A+B (mandatory)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_plan_day()
            await pilot.pause()
            await pilot.pause()
            opts = app.screen.query_one("#planp-list", SelectionList)
            assert set(opts.selected) == {1, 2}
            from src.lang import T as _T

            labels = " ".join(str(o.prompt) for o in opts._options)
            assert _T("plan_cut") in labels
            await pilot.press("ctrl+enter")
            await pilot.pause()
            await pilot.pause()
            by_id = {t.id: t for t in app.todos}
            assert by_id[1].planned_for == _day(0)
            assert by_id[3].planned_for == ""

    asyncio.run(t())


def test_rientro_ricorda_scarti(tmp_files):
    """Deseleziona -> conferma -> rientra: pianificati nascosti, scarto in fondo
    deselezionato con motivo; riseleziona -> skip azzerato e ripianificato."""
    from src.lang import T as _T

    async def t():
        app = make_app(_todos())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_plan_day()
            await pilot.pause()
            await pilot.pause()
            opts = app.screen.query_one("#planp-list", SelectionList)
            assert set(opts.selected) == {1, 2, 3}
            opts.deselect(3)
            await pilot.press("ctrl+enter")
            await pilot.pause()
            await pilot.pause()
            by_id = {t.id: t for t in app.todos}
            assert by_id[3].planned_for == ""
            assert by_id[3].plan_skip == _day(0)
            # rientro: 1,2 nascosti (gia' pianificati), solo C deselezionato
            app.action_plan_day()
            await pilot.pause()
            await pilot.pause()
            opts = app.screen.query_one("#planp-list", SelectionList)
            assert [o.value for o in opts._options] == [3]
            assert set(opts.selected) == set()
            labels = " ".join(str(o.prompt) for o in opts._options)
            assert _T("plan_skipped") in labels
            # riseleziona C: skip azzerato, 1,2 intoccati (additivo)
            opts.select(3)
            await pilot.press("ctrl+enter")
            await pilot.pause()
            await pilot.pause()
            by_id = {t.id: t for t in app.todos}
            assert by_id[3].planned_for == _day(0)
            assert by_id[3].plan_skip == ""
            assert by_id[1].planned_for == _day(0)
            assert by_id[2].planned_for == _day(0)

    asyncio.run(t())


def test_piano_completo_e_additivo(tmp_files):
    """Piano gia' fatto -> messaggio dedicato; conferma non toglie i pianificati."""

    async def t():
        todos = _todos()
        for t in todos[:2]:
            t.planned_for = _day(0)
        app = make_app(todos)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_plan_day()
            await pilot.pause()
            await pilot.pause()
            opts = app.screen.query_one("#planp-list", SelectionList)
            assert {o.value for o in opts._options} == {3}
            await pilot.press("ctrl+enter")
            await pilot.pause()
            await pilot.pause()
            by_id = {t.id: t for t in app.todos}
            assert by_id[1].planned_for == _day(0)
            assert by_id[2].planned_for == _day(0)
            assert by_id[3].planned_for == _day(0)
            # ora tutto pianificato -> messaggio piano completo
            app.action_plan_day()
            await pilot.pause()
            await pilot.pause()
            from src.lang import T as _T

            assert _T("planp_done") in screen_texts(app.screen)

    asyncio.run(t())


def test_conferma_con_s(tmp_files):
    """Tasto s (terminal-safe) conferma come ctrl+enter."""

    async def t():
        app = make_app(_todos())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_plan_day()
            await pilot.pause()
            await pilot.pause()
            await pilot.press("s")
            await pilot.pause()
            await pilot.pause()
            today = _day(0)
            by_id = {t.id: t for t in app.todos}
            assert by_id[1].planned_for == today
            assert by_id[2].planned_for == today

    asyncio.run(t())


def test_buongiorno_mostra_contesto_e_motivi(tmp_files):
    """Buongiorno unificato: contesto ex briefing, motivi inline,
    legend con salva e cornice che contiene i bottoni."""
    from textual.widgets import Button, SelectionList

    from src.lang import T as _T
    from src.screens import _hero_row as _hero

    async def t():
        todos = [
            make_todo(
                "P-piano",
                todo_id=1,
                planned_for=_day(0),
                stima_pomo=2,
            ),
            make_todo("A-ritardo", todo_id=2, due=_day(-1), priority=Priority.HIGH),
            make_todo("B-oggi", todo_id=3, due=_day(0)),
            make_todo(
                "Y-fatto",
                todo_id=4,
                done=True,
                completed_at=_day(-1) + " 10:00",
                pomodoro_log=[_day(-1) + " 10:30"],
            ),
        ]
        app = make_app(todos)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_plan_day()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "PlanProposalScreen"
            txt = screen_texts(app.screen)
            # titolo unificato (data formattata) + contesto ex briefing
            assert _T("menu_morning_t") in txt
            assert _T("brief_m_sec_today") in txt
            assert _hero(_T("brief_k_plan"), "1") in txt
            assert _hero(_T("brief_k_over"), "1") in txt
            assert _T("brief_m_load", s=2, c=12, h=6) in txt
            assert _T("brief_m_yest", d=1, p=1) in txt
            # motivi inline nelle label della proposta
            labels = " ".join(
                str(o.prompt)
                for o in app.screen.query_one("#planp-list", SelectionList)._options
            )
            assert _T("plan_overdue") in labels
            assert _T("rev_legend") in txt  # legend: s salva, non conferma
            # cornice condivisa: bottoni dentro il box
            box = app.screen.query_one("#planp-box").region
            for bid in ("#planp-confirm", "#planp-close"):
                r = app.screen.query_one(bid, Button).region
                assert r.x >= box.x and r.x + r.width <= box.x + box.width
                assert r.y >= box.y and r.y + r.height <= box.y + box.height

    asyncio.run(t())


def test_label_motivi_senza_id_e_senza_parentesi_vuote(tmp_files):
    """Label compatte: niente #id in coda (i motivi non vengono troncati),
    niente () quando i motivi sono vuoti."""
    from src.lang import T as _T
    from src.screens import PlanProposalScreen

    app = make_app(
        [
            make_todo(
                "Un titolo piuttosto lungo per spingere la riga oltre le colonne",
                todo_id=1,
                due=_day(-2),
                project="lavoro",
            ),
            make_todo("Semplice", todo_id=2),
        ]
    )
    screen = PlanProposalScreen(app.todos, lambda: None, today=_day(0))
    labels = {
        it.todo_id: screen._option_label(it.todo_id, it.reasons) for it in screen.rows
    }
    assert set(labels) == {1, 2}
    assert _T("plan_overdue") in labels[1]
    assert "#1" not in labels[1] and "#2" not in labels[2]
    assert "()" not in labels[1] and "()" not in labels[2]


def test_buongiorno_db_vuoto_mostra_messaggio(tmp_files):
    """Zero task attivi: il messaggio di vuoto e' sempre visibile (era un bug)."""
    from src.lang import T as _T

    async def t():
        app = make_app([])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_plan_day()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "PlanProposalScreen"
            txt = screen_texts(app.screen)
            assert _T("planp_empty") in txt
            assert _T("planp_additive") in txt

    asyncio.run(t())


def test_buongiorno_esc_non_scrive_nulla(tmp_files):
    """Esc/Annulla: planned_for e plan_skip restano intoccati."""
    from textual.widgets import SelectionList

    async def t():
        app = make_app(_todos())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_plan_day()
            await pilot.pause()
            await pilot.pause()
            opts = app.screen.query_one("#planp-list", SelectionList)
            opts.deselect(1)
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ != "PlanProposalScreen"
            by_id = {t.id: t for t in app.todos}
            assert all(t.planned_for == "" for t in by_id.values())
            assert all((t.plan_skip or "") == "" for t in by_id.values())

    asyncio.run(t())


def test_buongiorno_layout_terminale_piccolo(tmp_files):
    """Cornice fissa: Chiudi dentro il box anche a 80x24 e 70x20."""
    from textual.widgets import Button

    async def _once(w, h):
        app = make_app(_todos())
        async with app.run_test(size=(w, h)) as pilot:
            await pilot.pause()
            app.action_plan_day()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "PlanProposalScreen"
            box = app.screen.query_one("#planp-box").region
            btn = app.screen.query_one("#planp-close", Button).region
            assert btn.y >= box.y and btn.y + btn.height <= box.y + box.height
            assert btn.x >= box.x and btn.x + btn.width <= box.x + box.width

    async def t():
        for w, h in ((80, 24), (70, 20)):
            await _once(w, h)

    asyncio.run(t())


def test_buongiorno_prima_voce_giornata(tmp_files):
    from src.lang import T as _T

    cats = commands_module.menu_categories()
    day = [c for c in cats if c[0] == _T("menu_cat_day_t")][0]
    morning = [i for i in day[2] if i[2] == "action_plan_day"][0]
    assert morning[0] == _T("menu_morning_t")
    assert morning[3] == "P"
    assert day[2][0][0] == _T("menu_workflow_t")  # workflow resta prima voce
    assert "action_briefing_morning" not in [
        a for _c, _h, items in cats for _t, _hh, a, _s in items
    ]


def test_menu_palette_e_settings_ore(tmp_files):
    names = [action for _t, _h, action in commands_module.CarpeDiemMenuProvider.MENU_IT]
    assert "action_plan_day" in names

    async def t():
        app = make_app([make_todo("A")])
        async with app.run_test(size=(130, 55)) as pilot:
            await pilot.pause()
            app.action_open_settings()
            await pilot.pause()
            await pilot.pause()
            app.screen.query_one("#set-hours", Input).value = "4"
            await pilot.press("ctrl+enter")
            await pilot.pause()
            await pilot.pause()
            assert app.config["day_hours"] == 4
            saved = json.loads(m.CONFIG_FILE.read_text(encoding="utf-8"))
            assert saved["day_hours"] == 4

    asyncio.run(t())


def test_proposta_sopra_il_fold(tmp_files):
    """La lista proposta precede disponibilita'/eventi/slot nel DOM e sta
    sopra il fold dello scroll a 120x40 (il cuore della screen e' visibile
    all'apertura, senza scroll)."""

    async def t():
        app = make_app(_todos())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("P")
            await pilot.pause()
            await pilot.pause()
            scr = app.screen
            assert type(scr).__name__ == "PlanProposalScreen"
            ids = [
                w.id
                for w in scr.query_one("#planp-scroll").query("*")
                if w.id and w.id.startswith("planp-")
            ]
            assert ids.index("planp-list") < ids.index("planp-avail-label")
            assert ids.index("planp-list") < ids.index("planp-slots")
            scroll = scr.query_one("#planp-scroll")
            vp = scroll.scrollable_content_region
            sl = scr.query_one("#planp-list", SelectionList)
            assert sl.region.y < vp.y + vp.height

    asyncio.run(t())


def test_bottone_piano_giorno_conferma_e_apre(tmp_files):
    """Cross-link P->p: 'Piano giorno »' conferma e apre DailyPlanScreen."""

    async def t():
        from src.lang import T as _T

        app = make_app(_todos())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_plan_day()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "PlanProposalScreen"
            from textual.widgets import Button

            # screen_texts ignora i bottoni: il cross-link vive sul widget.
            assert (
                str(app.screen.query_one("#planp-day", Button).label)
                == _T("planp_goto_day")
            )
            await pilot.click("#planp-day")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "DailyPlanScreen"
            by_id = {t.id: t for t in app.todos}
            assert by_id[1].planned_for == _day(0)

    asyncio.run(t())


def test_piano_giorno_hint_replan_solo_con_finestra(tmp_files):
    """Hint P/G nel piano giorno solo con finestra attiva (mai default)."""

    async def t():
        from src.lang import T as _T

        todos = [make_todo("A-piano", todo_id=1, planned_for=_day(0))]
        app = make_app(todos)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_view_daily_plan()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "DailyPlanScreen"
            assert _T("plan_replan_hint") not in screen_texts(app.screen)
            await pilot.press("escape")
            await pilot.pause()
            app.config["day_window"] = {
                "date": _day(0),
                "start": "09:00",
                "end": "18:00",
                "events": [],
            }
            app.action_view_daily_plan()
            await pilot.pause()
            await pilot.pause()
            assert _T("plan_replan_hint") in screen_texts(app.screen)

    asyncio.run(t())
