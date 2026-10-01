"""Phase 2 Step P2-2 — E1/R1: facade plan() (docs/planner-phase2-plan.md §9).

E1: plan(request) ≡ path legacy su matrice (cancello permanente contro la
divergenza dei due path). R1: determinismo request→result.
Unica differenza documentata: evidence `due` normalizzata alla parte data
(conseguenza Phase-1 della projection, non del facade)."""

import random
from datetime import date, datetime

import src.planner.service as service_mod
from src.domain import calibration_factor, calibration_samples
from src.models import Priority
from src.planner import Planner, decide, plan
from src.planner.models import PlanningRequest, TimeWindow
from tests.conftest import make_todo

TODAY_S = "2026-09-10"
TODAY = date(2026, 9, 10)


def _win(h1, m1, h2, m2):
    return TimeWindow(datetime(2026, 9, 10, h1, m1), datetime(2026, 9, 10, h2, m2))


def _matrix():
    return [
        (
            "base",
            [
                make_todo("A-ritardo", todo_id=1, due="2026-09-09"),
                make_todo("B-oggi", todo_id=2, due=TODAY_S, priority=Priority.HIGH),
                make_todo("C-domani", todo_id=3, due="2026-09-11"),
                make_todo("D-nodue", todo_id=4, priority=Priority.LOW),
            ],
            6.0,
        ),
        (
            "planned-skip",
            [
                make_todo("GiaPian", todo_id=1, planned_for=TODAY_S),
                make_todo("Scartato", todo_id=2, plan_skip=TODAY_S),
                make_todo("Normale", todo_id=3),
            ],
            6.0,
        ),
        ("taglio", [make_todo(f"T{i}", todo_id=i) for i in range(1, 8)], 1.0),
        (
            "mandatory-sfora",
            [
                make_todo(f"Scaduto{i}", todo_id=i, due="2026-09-01")
                for i in range(1, 6)
            ],
            0.5,
        ),
        (
            "stime",
            [
                make_todo("Stimato", todo_id=1, stima_pomo=4, due=TODAY_S),
                make_todo("SenzaStima", todo_id=2, due=TODAY_S),
            ],
            6.0,
        ),
    ]


def _request(todos, hours, avail=()):
    return PlanningRequest(
        day=TODAY,
        tasks=todos,
        capacity_pomo=hours / 0.5,
        factor=calibration_factor(todos),
        availability=avail,
        sample_count=calibration_samples(todos),
    )


def test_e1_facade_uguale_a_legacy():
    avail = [_win(9, 0, 18, 0)]
    for name, todos, hours in _matrix():
        req = _request(todos, hours, avail)
        res = plan(req)
        legacy = Planner(todos, today=TODAY_S, hours=hours).propose()
        assert res.request is req, f"scenario {name}"
        assert res.plan == legacy, f"scenario {name}"
        assert res.plan.to_legacy() == legacy.to_legacy(), f"scenario {name}"
        assert res.scheduled == Planner.schedule(legacy, avail, ()), f"scenario {name}"
        assert res.decisions == decide(
            legacy, todos, sample_count=calibration_samples(todos)
        ), f"scenario {name}"


def test_e1_senza_availability_scheduled_none():
    todos = [make_todo("A", todo_id=1, due=TODAY_S)]
    res = plan(_request(todos, 6.0))
    assert res.scheduled is None
    assert len(res.decisions) == 1
    assert res.decisions[0].decision == "scheduled"


def test_e1_evidence_due_normalizzata():
    """Differenza documentata (non regressione): con due con orario,
    l'evidence del path request riporta la parte data (projection Phase 1),
    il flag overdue resta identico."""
    todos = [make_todo("A", todo_id=1, due="2026-09-09 14:00")]
    res = plan(_request(todos, 6.0))
    legacy = decide(Planner(todos, today=TODAY_S, hours=6.0).propose(), todos)
    assert res.decisions[0].evidence["due"] == "2026-09-09"
    assert legacy[0].evidence["due"] == "2026-09-09 14:00"
    assert res.decisions[0].evidence["overdue"] == legacy[0].evidence["overdue"] is True
    assert res.decisions[0].decision == legacy[0].decision
    assert res.decisions[0].reasons == legacy[0].reasons


def test_r1_shuffle_e_clock_stesso_risultato(monkeypatch):
    rng = random.Random(7)
    todos = [
        make_todo(f"T{i:03d}", todo_id=i, due=f"2026-09-{(i % 28) + 1:02d}")
        for i in range(1, 201)
    ]
    avail = [_win(9, 0, 18, 0)]
    expected = plan(_request(todos, 6.0, avail))

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 10, 15, 30)

    monkeypatch.setattr(service_mod, "datetime", _Frozen)
    for _ in range(3):
        shuffled = list(todos)
        rng.shuffle(shuffled)
        got = plan(_request(shuffled, 6.0, avail))
        assert got.plan == expected.plan
        assert got.scheduled == expected.scheduled
        assert got.decisions == expected.decisions
