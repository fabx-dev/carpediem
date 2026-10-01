"""Phase 3 Step P3-3 — M1: durate a convertitore unico (pomo_minutes).

Stessa aritmetica di prima in un solo punto: tabella letterale + spot che
gli slot misurano ancora 30min/pomo (nessuna deriva da float)."""

from datetime import date

from src.planner import capacity
from src.planner.models import DayPlan, PlanItem, TimeWindow
from src.planner.scheduler import schedule


def test_m1_tabella_minuti():
    assert [capacity.pomo_minutes(n) for n in (0, 1, 2, 4)] == [0, 30, 60, 120]
    assert capacity.pomo_minutes(-3) == 0
    assert capacity.pomo_minutes("xx") == 0
    assert capacity.pomo_minutes(None) == 0


def test_m1_slot_misura_30min_a_pomo():
    from datetime import datetime

    plan = DayPlan(
        day=date(2026, 9, 10),
        planned=(PlanItem(1, 10, (), 2, False), PlanItem(2, 5, (), 1, False)),
    )
    avail = [TimeWindow(datetime(2026, 9, 10, 9, 0), datetime(2026, 9, 10, 18, 0))]
    sched = schedule(plan, avail, ())
    got = [(s.end - s.start).total_seconds() // 60 for s in sched.scheduled]
    assert got == [60, 30]
