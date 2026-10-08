"""Righe senza orario nel piano giorno: divisorio etichettato + Why distinta.

La coda senza slot e' piano confermato senza collocazione (non scarto):
il divisorio lo dichiara e il Detail lo spiega (confermato + disponibilita'
insufficiente), con la stessa story di una riga timed.
"""

from datetime import datetime, timedelta

import pytest

from carpediem.lang import T as _T
from tests.conftest import make_app, make_todo, run, screen_texts


@pytest.fixture(autouse=True)
def _buongiorno_al_mattino(monkeypatch):
    """F1 clip-a-now: congela l'ora alle 08:00 di oggi (scenari mattutini)."""
    import carpediem.screens.plan as plan_mod

    fixed = datetime.strptime(f"{_day(0)} 08:00", "%Y-%m-%d %H:%M")

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

    monkeypatch.setattr(plan_mod, "datetime", _Frozen)


def _day(offset: int) -> str:
    return (datetime.now().date() + timedelta(days=offset)).strftime("%Y-%m-%d")


def _todos():
    return [
        make_todo("A", todo_id=1, planned_for=_day(0)),
        make_todo("B", todo_id=2, planned_for=_day(0)),
        make_todo("C", todo_id=3, planned_for=_day(0)),
    ]


def _window(start="09:00", end="09:30"):
    return {"date": _day(0), "start": start, "end": end, "events": []}


async def _open_plan(pilot, app):
    app.action_view_daily_plan()
    await pilot.pause()
    await pilot.pause()
    assert type(app.screen).__name__ == "DailyPlanScreen"


async def _goto(pilot, screen, tid):
    for _ in range(30):
        if screen._current()[0] == tid:
            return
        await pilot.press("down")
        await pilot.pause()
    raise AssertionError(f"riga {tid} non raggiunta")


def test_divisorio_etichettato_e_coda_senza_orario(tmp_files):
    async def t():
        app = make_app(_todos())
        app.config["day_window"] = _window()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            txt = screen_texts(app.screen)
            # B e C hanno perso la gara con A: sezione Non inseriti, mai
            # il contenitore generico "Senza orario".
            assert _T("plan_sec_pending") in txt  # divisorio nominato
            assert _T("plan_sec_outside") not in txt
            assert _T("plan_sec_noslot") not in txt
            assert "09:00–09:30 A" in txt  # A timed
            assert "09:00–09:30 B" not in txt  # B in coda, senza prefisso

    run(t())


def test_detail_coda_frase_unica(tmp_files):
    async def t():
        app = make_app(_todos())
        app.config["day_window"] = _window()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            await _goto(pilot, app.screen, 2)  # B in coda, senza slot
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "DetailScreen"
            txt = screen_texts(app.screen)
            # Un unico discorso: outcome + merito + causa (A occupa lo slot).
            # B ha perso la gara: mai "Confermato nel piano".
            assert (
                _T(
                    "why_noslot_sentence_tasks",
                    m=_T("why_frag_m_planned"),
                    c=_T("why_frag_c_tasks", t="A"),
                )
                in txt
            )
            assert "Confermato" not in txt
            assert _T("why_scheduled_noslot") not in txt  # assorbita nella frase
            assert _T("why_scheduled") not in txt
            assert _T("why_story_sched") not in txt  # assorbita
            assert _T("why_primary") not in txt  # assorbito
            assert _T("why_blocked_window") not in txt  # assorbito
            assert _T("why_sec_details") in txt  # dettagli fattuali restano

    run(t())


def test_noslot_sentence_nomina_eventi_con_escape():
    """La causa busy nomina gli eventi (escaping markup) nella frase unica."""
    import carpediem.planner.decisions as dec
    from carpediem.planner.models import PlanAlternative
    from carpediem.screens.views import _noslot_sentence

    d = dec.PlanningDecision(1, dec.SCHEDULED, (("plan_due_today", {}),), {}, None)
    alt = PlanAlternative(
        1, dec.SCHEDULED, "busy", {"needed_min": 30, "busy_titles": ("Pranzo [x]",)}
    )
    sent = _noslot_sentence(d, alt)
    assert sent is not None and r"Pranzo \[x]" in sent
    alt2 = PlanAlternative(1, dec.SCHEDULED, "busy", {"needed_min": 30})
    assert _noslot_sentence(d, alt2) is not None


def test_noslot_sentence_nomina_altri_task():
    """La causa tasks nomina i titoli (fallback #id), con escape markup."""
    import carpediem.planner.decisions as dec
    from carpediem.planner.models import PlanAlternative
    from carpediem.screens.views import _noslot_sentence

    d = dec.PlanningDecision(1, dec.SCHEDULED, (("plan_due_today", {}),), {}, None)
    alt = PlanAlternative(1, dec.SCHEDULED, "tasks", {"task_ids": (2, 9)})
    sent = _noslot_sentence(d, alt, {2: "Grosso [x]"})
    assert sent is not None and "Grosso" in sent and "#9" in sent
    assert "[x]" not in sent.replace("\\[x]", "")
    assert _noslot_sentence(d, alt) is not None  # senza titoli: #id
    many = PlanAlternative(1, dec.SCHEDULED, "tasks", {"task_ids": (1, 2, 3, 4)})
    many_sent = _noslot_sentence(d, many, {1: "A", 2: "B", 3: "C", 4: "D"})
    assert many_sent is not None and many_sent.count(",") == 3
    assert many_sent.endswith("…) occupano la fascia.")


def test_noslot_sentence_fallback_senza_pezzi():
    """_noslot_sentence pura: None se merito/causa non componibili.

    F5: kind ignoto -> fallback generico onesto (mai None silenzioso),
    merito ignoto -> None come prima (niente frase senza membro).
    """
    import carpediem.planner.decisions as dec
    from carpediem.planner.models import PlanAlternative
    from carpediem.screens.views import _noslot_sentence

    d = dec.PlanningDecision(1, dec.SCHEDULED, (("plan_x", {}),), {}, None)
    assert _noslot_sentence(d, None) is None
    assert (
        _noslot_sentence(
            d, PlanAlternative(1, dec.SCHEDULED, "window", {"needed_min": 5})
        )
        is None
    )
    d2 = dec.PlanningDecision(1, dec.SCHEDULED, (("plan_due_today", {}),), {}, None)
    sent = _noslot_sentence(d2, PlanAlternative(1, dec.SCHEDULED, "buco_nero", {}))
    assert sent is not None and "non classificato" in sent
    ok = _noslot_sentence(
        d2, PlanAlternative(1, dec.SCHEDULED, "busy", {"needed_min": 5})
    )
    assert ok is not None and "Blocco" not in ok and "Nel piano" not in ok


def test_detail_timed_non_contraddice_la_timeline(tmp_files):
    """Regressione card reale: task con slot visibile non deve mai dirsi
    senza orario — le alternative del Detail sono quelle della timeline
    (confermati), non del piano intero (Z non confermata ruba lo slot lì)."""
    from carpediem.planner import plan as plan_request
    from carpediem.screens.plan import build_planning_request

    async def t():
        app = make_app(
            [
                make_todo("Z", todo_id=9, due=_day(-1)),  # alto merito, NON confermato
                make_todo("A", todo_id=1, planned_for=_day(0)),
            ]
        )
        window = {"date": _day(0), "start": "09:00", "end": "09:30", "events": []}
        app.config["day_window"] = window
        # Nel piano intero A perde lo slot contro Z (prova della divergenza:
        # ora la causa nomina il rivale, non la finestra generica).
        full = plan_request(build_planning_request(app.todos, _day(0), 6.0, window))
        full_alts = {a.todo_id: a for a in full.alternatives}
        assert full_alts[1].blocked_by == "tasks"
        assert full_alts[1].detail["task_ids"] == (9,)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            txt = screen_texts(app.screen)
            assert "09:00–09:30 A" in txt  # timeline: A HA lo slot
            await _goto(pilot, app.screen, 1)
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "DetailScreen"
            dtxt = screen_texts(app.screen)
            assert _T("why_scheduled") in dtxt
            assert _T("why_scheduled_noslot") not in dtxt
            assert "Blocco:" not in dtxt

    run(t())


def test_detail_timed_etichetta_invariata(tmp_files):
    async def t():
        app = make_app(_todos())
        app.config["day_window"] = _window()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_plan(pilot, app)
            await _goto(pilot, app.screen, 1)  # A timed
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            txt = screen_texts(app.screen)
            assert _T("why_scheduled") in txt
            assert _T("why_scheduled_noslot") not in txt

    run(t())


def test_b10_tasks_senza_slot_etichetta_noslot(tmp_files):
    """B10: SCHEDULED unscheduled per gara persa -> mai etichetta liscia."""
    import carpediem.planner.decisions as dec
    import carpediem.planner.models as pmod
    from carpediem.lang import T
    from carpediem.screens.views import DetailScreen

    today = _day(0)

    def t():
        async def inner():
            app = make_app(
                [
                    make_todo("A", todo_id=1, planned_for=today),
                    make_todo("B", todo_id=2),
                ]
            )
            d = dec.PlanningDecision(1, dec.SCHEDULED, ())
            alt = pmod.PlanAlternative(1, dec.SCHEDULED, "tasks", {"task_ids": (2,)})
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.push_screen(
                    DetailScreen(
                        app.todos[0],
                        app.todos,
                        today=today,
                        hours=6.0,
                        decisions=(d,),
                        alternatives={1: alt},
                    )
                )
                await pilot.pause()
                await pilot.pause()
                assert type(app.screen).__name__ == "DetailScreen"
                txt = screen_texts(app.screen)
                assert T("why_scheduled_noslot_tasks") in txt
                assert "Confermato" not in txt
                assert T("why_scheduled") not in txt

        return inner()

    run(t())
