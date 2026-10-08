"""F5 spiegabilita': story tight, cause con numeri, coda Buongiorno, header piano."""

import asyncio
from datetime import datetime, timedelta

import pytest

import src.planner.decisions as dec
from src.lang import T as _T
from src.planner.narrative import explain_decision, explain_proposed
from src.planner.phrases import phrase_for
from src.screens.plan import PlanProposalScreen
from src.screens.views import plan_context
from tests.conftest import make_app, make_todo, screen_texts


def _day(offset: int) -> str:
    return (datetime.now().date() + timedelta(days=offset)).strftime("%Y-%m-%d")


@pytest.fixture(autouse=True)
def _buongiorno_al_mattino(monkeypatch):
    """Freeze 08:00 per i pilot (scenari mattutini deterministici)."""
    import src.screens.plan as plan_mod

    fixed = datetime.strptime(f"{_day(0)} 08:00", "%Y-%m-%d %H:%M")

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

    monkeypatch.setattr(plan_mod, "datetime", _Frozen)


def _d(kind, reasons, evidence=None):
    return dec.PlanningDecision(1, kind, tuple(reasons), dict(evidence or {}), None)


def _ev(**kw):
    base = {"overdue": False, "priority": "", "mandatory": False}
    base.update(kw)
    return base


def test_story_tight_con_slack_misurato():
    d = _d(dec.SCHEDULED, [("plan_due_today", {})], _ev(slack_min=45, mandatory=True))
    ref = explain_decision(d)
    assert ref.key == "why_story_sched_tight"
    assert _T(ref.key)  # chiave reale it/en
    p = explain_proposed(d)
    assert p.key == "why_story_prop_tight"


def test_story_due_today_senza_slack_invariata():
    d = _d(dec.SCHEDULED, [("plan_due_today", {})], _ev(mandatory=True))
    assert explain_decision(d).key == "why_story_sched_due_today"
    assert explain_proposed(d).key == "why_story_prop_due_today"


def test_frase_gap_window_con_numeri_veri():
    for family, key in (
        ("blocked-line", "why_blocked_window_gap"),
        ("blocked-frag", "why_frag_c_window_gap"),
    ):
        ref = phrase_for(
            "window", family, {"needed_min": 90, "max_gap_min": 30, "gap_count": 3}
        )
        assert ref.key == key
        assert ref.params == {"g": 30, "n": 90}
        txt = _T(ref.key, **ref.params)
        assert "90" in txt and "30" in txt


def test_frase_gap_busy_con_nomi_e_numeri():
    ref = phrase_for(
        "busy",
        "blocked-frag",
        {"busy_titles": "Riunione", "needed_min": 60, "max_gap_min": 25},
    )
    assert ref.key == "why_frag_c_busy_named_gap"
    assert _T(ref.key, **ref.params).count("Riunione") == 1
    ref_line = phrase_for("busy", "blocked-line", {"needed_min": 60, "max_gap_min": 25})
    assert ref_line.key == "why_blocked_busy_gap"


def test_frase_window_senza_numeri_legacy():
    assert phrase_for("window", "blocked-frag", {}).key == "why_frag_c_window"
    assert phrase_for("window", "blocked-line", {}).key == "why_blocked_window"


def test_kind_ignoto_fallback_onesto():
    for family, key in (
        ("blocked-line", "why_blocked_unknown"),
        ("blocked-frag", "why_frag_c_unknown"),
    ):
        ref = phrase_for("buco_nero_2099", family, {})
        assert ref.key == key
        assert _T(ref.key)


def test_buongiorno_coda_con_causa_reale():
    todos = [make_todo("Big", todo_id=1, stima_pomo=3)]
    screen = PlanProposalScreen(
        todos,
        lambda *a: None,
        today=_day(0),
        hours=6.0,
        now=datetime.strptime(f"{_day(0)} 08:00", "%Y-%m-%d %H:%M"),
    )
    screen.start_text = "09:00"
    screen.end_text = "10:00"
    screen._refresh_sched()
    lines = screen._slot_lines()
    # 90m in 60m: coda con causa dai numeri reali di diagnose.
    assert _T("planp_slots_un", t="")[:12] in lines
    assert "Big" in lines and "90" in lines and "60" in lines
    assert "non viene spezzato" in lines


def test_piano_header_mostra_minuti_liberi(tmp_files):
    async def t():
        app = make_app([make_todo("A", todo_id=1, planned_for=_day(0), stima_pomo=2)])
        app.config["day_window"] = {
            "date": _day(0),
            "start": "09:00",
            "end": "18:00",
            "events": [],
            "allday": [],
        }
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_view_daily_plan()
            await pilot.pause()
            await pilot.pause()
            txt = screen_texts(app.screen)
            assert _T("plan_sec_window", window="09:00–18:00") in txt
            assert _T("plan_time_left", m=540) in txt

    asyncio.run(t())


def test_why_tight_end_to_end_da_plan_context():
    todos = [make_todo("U", todo_id=1, due=f"{_day(0)} 10:00", stima_pomo=1)]
    window = {"date": _day(0), "start": "09:00", "end": "18:00", "events": []}
    now = datetime.strptime(f"{_day(0)} 08:00", "%Y-%m-%d %H:%M")
    decisions, _alts = plan_context(todos, _day(0), 6.0, window, now=now)
    assert decisions
    d = next(x for x in decisions if x.todo_id == 1)
    assert d.evidence.get("slack_min") == 90  # (10:00-08:00) - 30m
    assert explain_decision(d).key == "why_story_sched_tight"


def test_today_window_gate():
    app = make_app([make_todo("A", todo_id=1)])
    today = _day(0)
    app.config["day_window"] = {"date": today, "start": "09:00", "end": "18:00"}
    assert app._today_window(today)["start"] == "09:00"
    assert app._today_window("2000-01-01") is None
    app.config.pop("day_window")
    assert app._today_window(today) is None
