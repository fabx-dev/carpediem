"""Test reason keys del Planner (compatibilita' congelata con i18n e UI)."""

from src.lang import STRINGS
from src.planner import explain


def test_chiavi_congelate():
    """I valori restano i letterali legacy (rinominarli rompe T() e screen)."""
    assert explain.OVERDUE == "plan_overdue"
    assert explain.DUE_TODAY == "plan_due_today"
    assert explain.DUE_TOMORROW == "plan_due_tomorrow"
    assert explain.PRIO == "plan_prio"
    assert explain.STALE == "plan_stale"
    assert explain.PLANNED == "plan_planned"
    assert explain.CALIBRATED == "plan_calibrated"
    assert explain.CUT == "plan_cut"
    assert explain.SKIPPED == "plan_skipped"
    assert explain.ALL == frozenset(
        {
            "plan_overdue",
            "plan_due_today",
            "plan_due_tomorrow",
            "plan_prio",
            "plan_stale",
            "plan_planned",
            "plan_calibrated",
            "plan_cut",
            "plan_skipped",
        }
    )


def test_chiavi_presenti_nel_catalogo_i18n():
    for lang in STRINGS:
        for key in explain.ALL:
            assert key in STRINGS[lang], (lang, key)


def test_builder():
    assert explain.overdue() == ("plan_overdue", {})
    assert explain.due_today() == ("plan_due_today", {})
    assert explain.due_tomorrow() == ("plan_due_tomorrow", {})
    assert explain.prio() == ("plan_prio", {})
    assert explain.stale(9) == ("plan_stale", {"n": 9})
    assert explain.planned() == ("plan_planned", {})
    assert explain.calibrated(2.0) == ("plan_calibrated", {"f": "x2.0"})
    assert explain.cut() == ("plan_cut", {})
    assert explain.skipped() == ("plan_skipped", {})
