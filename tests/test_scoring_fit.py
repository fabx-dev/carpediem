"""F3 scoring secondario: pesi intoccati, slack/durata a parita' di score."""

from datetime import datetime

from carpediem.planner import capacity, constraints
from carpediem.planner.decisions import decide, refine_with_schedule
from carpediem.planner.models import DayPlan, PlanItem, TaskView, TimeWindow
from carpediem.planner.scheduler import schedule
from carpediem.planner.scoring import OVERDUE_SCORE, rank_key

DAY_S = "2026-10-08"


def at(h, m=0):
    return datetime(2026, 10, 8, h, m)


def view(tid, due="", estimate=1):
    return TaskView(id=tid, state="attivo", due=due, estimate_pomo=estimate)


def test_pesi_primari_congelati():
    assert OVERDUE_SCORE == 100
    import carpediem.planner.scoring as s

    assert (s.DUE_TODAY_SCORE, s.DUE_TOMORROW_SCORE) == (60, 30)
    assert (s.PRIO_SCORES["alta"], s.STALE_SCORE, s.PLANNED_SCORE) == (20, 15, 5)


def test_rank_key_legacy_senza_contesto():
    a = view(1, due=DAY_S)
    assert rank_key((a, 10, ())) == (-10, DAY_S, 1)
    b = view(2)
    assert rank_key((b, 10, ())) == (-10, "9999", 2)


def test_rank_key_slack_crescente_a_pari_score():
    loose = view(1, due=DAY_S, estimate=1)
    tight = view(2, due=DAY_S, estimate=1)
    deadlines = {1: (DAY_S, "18:00"), 2: (DAY_S, "10:00")}
    key_loose = rank_key((loose, 10, ()), now=at(9), deadlines=deadlines)
    key_tight = rank_key((tight, 10, ()), now=at(9), deadlines=deadlines)
    assert key_tight < key_loose  # slack 30 prima di slack 480
    # Senza contesto: ordine legacy (stesso due, vince l'id).
    assert rank_key((loose, 10, ())) < rank_key((tight, 10, ()))


def test_rank_key_durata_crescente_a_pari_slack():
    breve = view(1, due=DAY_S, estimate=1)
    lungo = view(2, due=DAY_S, estimate=4)
    # Stesso slack (150): 12:00-30m e 13:30-120m da 09:00.
    deadlines = {1: (DAY_S, "12:00"), 2: (DAY_S, "13:30")}
    kb = rank_key((breve, 10, ()), now=at(9), deadlines=deadlines)
    kl = rank_key((lungo, 10, ()), now=at(9), deadlines=deadlines)
    assert kb[1] == kl[1] == 150
    assert kb < kl  # stesso slack-ordine, il breve riempie meglio i buchi


def test_rank_key_senza_deadline_oggi_in_coda():
    dated = view(1, due=DAY_S, estimate=1)
    plain = view(2, due="", estimate=1)
    deadlines = {1: (DAY_S, "12:00")}
    kd = rank_key((dated, 10, ()), now=at(9), deadlines=deadlines)
    kp = rank_key((plain, 10, ()), now=at(9), deadlines=deadlines)
    assert kd < kp


def test_allocate_preferisce_scadenza_stretta_a_pari_score():
    a = view(1, due=DAY_S, estimate=1)
    b = view(2, due=DAY_S, estimate=1)
    scored = [(a, 20, [], False), (b, 20, [], False)]
    deadlines = {1: (DAY_S, "18:00"), 2: (DAY_S, "10:00")}
    # Capacita' per un solo task: con now vince B (slack 30).
    out = capacity.allocate(
        scored,
        today_s=DAY_S,
        capacity=1.0,
        calib=None,
        now=at(9),
        deadlines=deadlines,
    )
    planned = [t.id for t, _s, _r, _m in out if not any(k == "plan_cut" for k, _ in _r)]
    assert planned == [2]
    # Senza contesto: legacy (stesso due, vince l'id minore).
    out_legacy = capacity.allocate(scored, today_s=DAY_S, capacity=1.0, calib=None)
    planned_legacy = [
        t.id for t, _s, _r, _m in out_legacy if not any(k == "plan_cut" for k, _ in _r)
    ]
    assert planned_legacy == [1]


def test_partition_secondario_stabile():
    a = view(1, due=DAY_S, estimate=1)
    b = view(2, due=DAY_S, estimate=2)
    a_skip = TaskView(id=1, state="attivo", due=DAY_S, plan_skip=DAY_S, estimate_pomo=1)
    b_skip = TaskView(id=2, state="attivo", due=DAY_S, plan_skip=DAY_S, estimate_pomo=2)
    scored = [(a_skip, 10, [], False), (b_skip, 10, [], False)]
    _cands, skipped = constraints.partition(
        scored, DAY_S, now=at(9), deadlines={1: (DAY_S, "18:00")}
    )
    assert [t.id for t, _s, _r, _m in skipped] == [1, 2]
    assert a.id == 1 and b.id == 2


def test_decide_evidence_slack_e_residuo():
    from datetime import date

    item = PlanItem(1, 60, (("plan_due_today", {}),), 2, True)
    plan = DayPlan(
        day=date(2026, 10, 8),
        planned=(item,),
        capacity_pomo=12.0,
        planned_pomo=2,
    )
    todos = [view(1, due=DAY_S, estimate=2)]
    deadlines = {1: (DAY_S, "12:00")}
    (d,) = decide(plan, todos, now=at(9), deadlines=deadlines)
    # slack = (12:00 - 09:00) - 60m = 120.
    assert d.evidence["slack_min"] == 120
    assert d.evidence["residual_pomo"] == 10
    (d_legacy,) = decide(plan, todos)
    assert "slack_min" not in d_legacy.evidence
    assert d_legacy.evidence["residual_pomo"] == 10


def test_refine_evidence_gap_e_remaining():
    from datetime import date

    item = PlanItem(1, 10, (), 1, False)
    plan = DayPlan(
        day=date(2026, 10, 8),
        planned=(item,),
        capacity_pomo=12.0,
        planned_pomo=1,
    )
    sched = schedule(plan, [TimeWindow(at(9), at(12))])
    (d,) = decide(plan, [view(1, estimate=1)])
    (r,) = refine_with_schedule((d,), sched, now=at(9))
    # Un gap da 180m, task da 30m: waste 150; liberi 180m.
    assert r.evidence["gap_waste_min"] == 150
    assert r.evidence["remaining_min"] == 180
    (r_legacy,) = refine_with_schedule((d,), sched)
    assert "gap_waste_min" not in r_legacy.evidence
    assert "remaining_min" not in r_legacy.evidence
