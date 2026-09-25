"""Explanation layer M3 UX: explain_decision() deterministico e puro.

Niente pilot/Textual: PlanningDecision costruite a mano o via Planner.
Verifica: un template per stato/variante, determinismo, solo lettura
delle reasons/evidence reali, parita' it/en, planner invariato.
"""

import src.lang as lang
import src.planner.decisions as dec
from src.planner import Planner, decide
from src.planner.explain import (
    CUT,
    DUE_TODAY,
    OVERDUE,
    PRIO,
    SKIPPED,
)
from src.planner.narrative import explain_decision, story_keys
from tests.conftest import make_todo

TODAY = "2026-09-10"


def _d(kind, reasons, evidence=None):
    return dec.PlanningDecision(1, kind, tuple(reasons), dict(evidence or {}), None)


def _ev(**kw):
    base = {"overdue": False, "priority": "", "mandatory": False}
    base.update(kw)
    return base


def test_sette_template_distinti():
    assert len(story_keys()) == 7
    assert all(k.startswith("why_story_") for k in story_keys())


def test_scheduled_overdue():
    d = _d(dec.SCHEDULED, [(OVERDUE, {})], _ev(overdue=True, mandatory=True))
    assert explain_decision(d) == ("why_story_sched_overdue", {})


def test_scheduled_overdue_da_sola_evidence():
    # mandatory senza reason overdue esplicita: l'evidence basta.
    d = _d(dec.SCHEDULED, [("plan_due_today", {})], _ev(overdue=True))
    assert explain_decision(d) == ("why_story_sched_overdue", {})


def test_scheduled_due_today():
    d = _d(dec.SCHEDULED, [(DUE_TODAY, {})], _ev())
    assert explain_decision(d) == ("why_story_sched_due_today", {})


def test_scheduled_prio():
    d = _d(dec.SCHEDULED, [(PRIO, {})], _ev(priority="alta"))
    assert explain_decision(d) == ("why_story_sched_prio", {})


def test_scheduled_fallback():
    d = _d(dec.SCHEDULED, [("plan_due_tomorrow", {})], _ev())
    assert explain_decision(d) == ("why_story_sched", {})


def test_not_scheduled_cut():
    d = _d(dec.NOT_SCHEDULED, [(CUT, {})], _ev())
    assert explain_decision(d) == ("why_story_cut", {})


def test_deferred():
    d = _d(dec.DEFERRED, [(SKIPPED, {})], _ev())
    assert explain_decision(d) == ("why_story_deferred", {})


def test_constrained():
    d = _d(dec.CONSTRAINED, [(OVERDUE, {})], _ev(overdue=True, mandatory=True))
    assert explain_decision(d) == ("why_story_constrained", {})


def test_reasons_vuote_niente_testo_inventato():
    assert explain_decision(_d(dec.SCHEDULED, [], _ev())) is None


def test_deterministico():
    d = _d(dec.SCHEDULED, [(OVERDUE, {})], _ev(overdue=True))
    assert explain_decision(d) == explain_decision(d)


def test_priorita_overdue_su_due_today():
    d = _d(dec.SCHEDULED, [(OVERDUE, {}), (DUE_TODAY, {})], _ev(overdue=True))
    assert explain_decision(d) == ("why_story_sched_overdue", {})


def test_it_en_parita_e_distinte(italian_lang):
    for key in sorted(story_keys()):
        it = lang.STRINGS["it"][key]
        en = lang.STRINGS["en"][key]
        assert it != key and en != key and it != en
    lang.set_lang("en")
    try:
        assert lang.T("why_story_cut") != lang.STRINGS["it"]["why_story_cut"]
    finally:
        lang.set_lang("it")


def test_decisioni_reali_del_planner_restano_inariate():
    todos = [
        make_todo("A-ritardo", todo_id=1, due="2026-09-01"),
        make_todo("B-nodue", todo_id=2),
        make_todo("C-skip", todo_id=3, plan_skip=TODAY),
    ]
    plan = Planner(todos, today=TODAY, hours=0.5).propose()
    decisions = decide(plan, todos)
    by_id = {d.todo_id: d for d in decisions}
    assert by_id[1].decision == dec.SCHEDULED
    assert by_id[2].decision == dec.NOT_SCHEDULED
    assert by_id[3].decision == dec.DEFERRED
    stories = {d.todo_id: explain_decision(d) for d in decisions}
    assert stories[1][0] == "why_story_sched_overdue"
    assert stories[2][0] == "why_story_cut"
    assert stories[3][0] == "why_story_deferred"
    # il planner non e' cambiato: le decisioni sono identiche con o senza story
    assert {d.todo_id: d.decision for d in decisions} == {
        1: dec.SCHEDULED,
        2: dec.NOT_SCHEDULED,
        3: dec.DEFERRED,
    }
