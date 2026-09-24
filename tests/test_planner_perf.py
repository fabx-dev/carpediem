"""Baseline di performance M1 del planning engine (50/100/500/1000 task).

Non ottimizza nulla: fissa una baseline ripetibile (seed deterministico,
vincoli realistici) contro cui confrontare le fasi successive. Le soglie
sono larghissime per non rendere flaky la CI su runner lenti: servono a
catturare regressioni di ordini di grandezza, non a fare benchmarking fine.
Baseline locale 2026-09-24 (propose()+schedule(), ms):
50 -> ~0.3ms, 100 -> ~0.6ms, 500 -> ~2.9ms, 1000 -> ~5.4ms.
"""

import random
import time
from datetime import datetime

from src.models import Priority
from src.planner import Planner
from src.planner.models import TimeWindow
from tests.conftest import make_todo

TODAY = "2026-09-10"
PRIOS = [Priority.HIGH, Priority.MEDIUM, Priority.LOW]

# Soglie CI larghe (secondi): solo rete anti-collasso, non gara di velocita'.
LIMITS = {50: 10.0, 100: 15.0, 500: 30.0, 1000: 60.0}


def _many_todos(n, seed=7):
    rng = random.Random(seed)
    todos = []
    for i in range(1, n + 1):
        due = rng.choice(["", TODAY, "2026-09-11", "2026-09-01", "2026-09-20"])
        todos.append(
            make_todo(
                f"T{i}",
                todo_id=i,
                due=due,
                priority=rng.choice(PRIOS),
                project=rng.choice(["", "alfa", "beta", "gamma"]),
                stima_pomo=rng.choice([0, 1, 1, 2, 3, 5]),
                planned_for=TODAY if rng.random() < 0.1 else "",
                plan_skip=TODAY if rng.random() < 0.05 else "",
            )
        )
    return todos


def _bench(n):
    todos = _many_todos(n)
    plan = Planner(todos, today=TODAY, hours=6.0).propose()
    avail = [TimeWindow(datetime(2026, 9, 10, 9, 0), datetime(2026, 9, 10, 18, 0))]
    t0 = time.perf_counter()
    plan = Planner(todos, today=TODAY, hours=6.0).propose()
    Planner.schedule(plan, avail)
    dt = time.perf_counter() - t0
    print(f"\nbench n={n}: {dt * 1000:.1f}ms planned={len(plan.planned)}")
    assert dt < LIMITS[n], f"regressione performance: n={n} in {dt:.1f}s"
    return dt


def test_bench_50():
    _bench(50)


def test_bench_100():
    _bench(100)


def test_bench_500():
    _bench(500)


def test_bench_1000():
    _bench(1000)
