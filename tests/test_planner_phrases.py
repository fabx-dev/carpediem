"""Contratto PhraseRef: il Planner produce riferimenti, la UI li renderizza.

Ogni kind valido risolve in una chiave esistente it/en con params coperti;
mapping dinamici non verificati (T(f"...")) vietati per il Planner.
"""

import pathlib
import string

from src.lang import STRINGS
from src.planner import Planner
from src.planner.models import BLOCKED_KINDS
from src.planner.narrative import explain_decision, explain_proposed, story_keys
from src.planner.phrases import PhraseRef, phrase_for
from src.planner.replan import ADDED, DROPPED, KEPT, MOVED
from tests.conftest import make_todo

TODAY = "2026-09-10"
_VALID_ORIGINS = {"story", "blocker", "replan", "decision"}


def _placeholders(key: str, lang: str = "it") -> set:
    text = STRINGS[lang][key]
    return {fn for _, fn, _, _ in string.Formatter().parse(text) if fn}


def test_phraseref_forma_e_compat_tuple():
    ref = PhraseRef("k", {"a": 1}, "story")
    assert ref.key == "k" and ref.params == {"a": 1} and ref.origin == "story"
    assert tuple(ref)[:2] == ("k", {"a": 1})
    assert PhraseRef("k").params == {} and PhraseRef("k").origin == ""


def test_narrative_tutti_rami_con_chiavi_valide():
    todos = [
        make_todo("A-ritardo", todo_id=1, due="2026-09-01"),
        make_todo("B-nodue", todo_id=2),
        make_todo("C-skip", todo_id=3, plan_skip=TODAY),
    ]
    plan = Planner(todos, today=TODAY, hours=0.5).propose()
    seen = set()
    from src.planner import decide

    for d in decide(plan, todos):
        for fn in (explain_decision, explain_proposed):
            ref = fn(d)
            if ref is None:
                continue
            assert isinstance(ref, PhraseRef)
            assert ref.origin == "story"
            assert ref.key in STRINGS["it"] and ref.key in STRINGS["en"]
            for lang in ("it", "en"):
                assert _placeholders(ref.key, lang) <= set(ref.params), ref.key
            seen.add(ref.key)
    # Tutti i rami sched/cut/deferred esercitati dallo scenario.
    assert "why_story_sched_overdue" in seen
    assert "why_story_cut" in seen
    assert "why_story_deferred" in seen
    assert seen <= story_keys()


def test_kind_mapping_blocked_replan_decision():
    blocked_details = {
        "user_skip": {},
        "capacity": {},
        "deadline": {"deadline": "10:00"},
        "busy": {},
        "window": {},
        "duration": {},
        "tasks": {"task_ids": (1,), "task_names": "A"},
    }
    for kind in BLOCKED_KINDS:
        for family in ("blocked-line", "blocked-frag"):
            if family == "blocked-frag" and kind == "user_skip":
                continue  # DEFERRED non ha frammento per disegno
            ref = phrase_for(kind, family, blocked_details[kind])
            assert ref.origin == "blocker"
            assert ref.key in STRINGS["it"] and ref.key in STRINGS["en"]
            for lang in ("it", "en"):
                assert _placeholders(ref.key, lang) <= set(ref.params), ref.key
    assert phrase_for("busy", "blocked-line", {"busy_titles": "X"}).params == {"e": "X"}
    assert phrase_for(
        "tasks", "blocked-line", {"task_ids": (1,), "task_names": "A"}
    ).params == {"t": "A"}
    for kind in (KEPT, MOVED, DROPPED, ADDED):
        ref = phrase_for(kind, "replan")
        assert ref.origin == "replan"
        assert ref.key in STRINGS["it"] and ref.key in STRINGS["en"]
        assert ref.params == {}
    for kind in (
        "scheduled",
        "not_scheduled",
        "deferred",
        "constrained",
        "proposed",
        "no_decision",
    ):
        ref = phrase_for(kind, "decision")
        assert ref.origin == "decision"
        assert ref.key in STRINGS["it"] and ref.key in STRINGS["en"]


def test_kind_ignoto_e_detail_mancante_sollevano():
    import pytest

    with pytest.raises(KeyError):
        phrase_for("buco_nero", "blocked-line", {})
    with pytest.raises(KeyError):
        phrase_for("capacity", "famiglia_ignota", {})
    with pytest.raises(KeyError):
        phrase_for("deadline", "blocked-line", {})
    with pytest.raises(KeyError):
        phrase_for("tasks", "blocked-frag", {"task_ids": (1,)})


def test_origin_solo_vocabolario_valido():
    details = {
        "deadline": {"deadline": "10:00"},
        "tasks": {"task_ids": (1,), "task_names": "A"},
    }
    for kind in BLOCKED_KINDS:
        assert (
            phrase_for(kind, "blocked-line", details.get(kind, {})).origin
            in _VALID_ORIGINS
        )


def test_niente_t_f_dinamici_planner():
    """Il mapping dinamico T(f\"why_blocked_…\") e' sparito: grep-test."""
    hits = []
    for path in ("src/screens/views.py", "src/screens/plan.py", "src/cli.py"):
        for i, line in enumerate(
            pathlib.Path(path).read_text(encoding="utf-8").splitlines(), 1
        ):
            if 'T(f"' in line and "why_blocked" in line:
                hits.append(f"{path}:{i}")
    assert hits == [], hits


def test_chiavi_dinamiche_legittime_limitate():
    """help/workflow restano dinamici ma bounded: ogni chiave esiste."""
    for i in range(1, 6):
        assert f"help_l{i}" in STRINGS["it"] and f"help_l{i}" in STRINGS["en"]
    for i in range(1, 6):
        for suffix in ("t", "b"):
            key = f"workflow_s{i}_{suffix}"
            assert key in STRINGS["it"] and key in STRINGS["en"], key
