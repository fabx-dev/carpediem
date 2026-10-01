"""Phase 2 Step P2-5 — D1: contratto estimation (docs/planner-phase2-plan.md §7).

La matematica resta in domain fino a Phase 5 per decisione esplicita; qui
si fissa il CONTRATTO (tabella letterale, non tautologica: i valori attesi
sono calcolati a mano dalla policy documentata) e il guard che ne fa
capacity.py l'unico importatore nel planner. Solo test, zero produzione.
"""

from src.planner import capacity
from src.planner.models import todo_to_task
from tests.conftest import make_todo

# (stima, factor) -> atteso. Policy: base = stima o 1 se assente;
# factor None/garbage = base; altrimenti clamp [0.5, 3.0], max(1, round()).
# Nota: round() Python e' banker's (round(0.5)=0, round(2.5)=2).
ESTIMATE_TABLE = [
    (0, None, 1),
    (0, 2.0, 2),
    (1, None, 1),
    (1, 0.4, 1),  # clamp 0.5 -> round 0 -> max 1
    (1, 0.6, 1),
    (1, 1.0, 1),
    (2, None, 2),
    (2, 0.5, 1),
    (2, 2.0, 4),
    (2, 99.0, 6),  # clamp 3.0
    (3, 3.0, 9),
    (5, 0.5, 2),  # round(2.5) banker's = 2
    (2, "xx", 2),  # factor garbage = base
    (2, -1, 1),  # clamp 0.5
    ("x", 1.0, 1),  # stima garbage = base 1
]


def test_d1_tabella_stime_letterale():
    for base, factor, expected in ESTIMATE_TABLE:
        t = make_todo("T", todo_id=1, stima_pomo=base)
        assert capacity.estimate(t, factor) == expected, (base, factor)
        v = todo_to_task(t)
        assert capacity.estimate(v, factor) == expected, (base, factor)


def test_d1_normalize_factor_bordi():
    assert capacity.normalize_factor(None) is None
    assert capacity.normalize_factor("xx") is None
    assert capacity.normalize_factor(1.0) == 1.0
    assert capacity.normalize_factor(0.5) == 0.5
    assert capacity.normalize_factor(3.0) == 3.0
    assert capacity.normalize_factor(0.1) == 0.5
    assert capacity.normalize_factor(0.0) == 0.5
    assert capacity.normalize_factor(99.0) == 3.0
    assert capacity.normalize_factor(-2.0) == 0.5
