"""Test planner deterministico (funzione pura, nessun file)."""

from src.models import Priority
from src.plan import plan_day
from tests.conftest import make_todo

TODAY = "2026-09-10"


def _ids(plan):
    return [t_id for t_id, _s, _r in plan]


def _reasons(plan, t_id):
    for pid, _s, reasons in plan:
        if pid == t_id:
            return [k for k, _p in reasons]
    raise AssertionError(t_id)


def test_ordine_scadenze():
    todos = [
        make_todo("D-nodue", todo_id=4, priority=Priority.HIGH),
        make_todo("C-domani", todo_id=3, due="2026-09-11", priority=Priority.HIGH),
        make_todo("B-oggi", todo_id=2, due="2026-09-10", priority=Priority.HIGH),
        make_todo("A-ritardo", todo_id=1, due="2026-09-09", priority=Priority.LOW),
    ]
    plan = plan_day(todos, TODAY)
    assert _ids(plan) == [1, 2, 3, 4]
    scores = {t_id: s for t_id, s, _r in plan}
    assert scores == {1: 100, 2: 80, 3: 50, 4: 20}
    assert _reasons(plan, 1) == ["plan_overdue"]
    assert _reasons(plan, 2) == ["plan_due_today", "plan_prio"]
    assert _reasons(plan, 3) == ["plan_due_tomorrow", "plan_prio"]
    assert _reasons(plan, 4) == ["plan_prio"]


def test_priorita_a_pari_merito():
    todos = [
        make_todo("L", todo_id=1, due=TODAY, priority=Priority.LOW),
        make_todo("M", todo_id=2, due=TODAY, priority=Priority.MEDIUM),
        make_todo("H", todo_id=3, due=TODAY, priority=Priority.HIGH),
    ]
    assert _ids(plan_day(todos, TODAY)) == [3, 2, 1]


def test_fatti_e_sospesi_esclusi():
    todos = [
        make_todo("done", todo_id=1, due="2026-09-01", done=True),
        make_todo("paused", todo_id=2, due="2026-09-01", paused=True),
        make_todo("open", todo_id=3, due="2026-09-01"),
    ]
    assert _ids(plan_day(todos, TODAY)) == [3]


def test_gia_in_piano():
    todos = [make_todo("E", todo_id=1, planned_for=TODAY)]
    plan = plan_day(todos, TODAY)
    assert plan[0][1] == 15  # 10 media + 5 piano
    assert _reasons(plan, 1) == ["plan_planned"]


def test_taglio_capacita():
    todos = [
        make_todo("A-oggi", todo_id=1, due=TODAY, stima_pomo=2),
        make_todo(
            "B-domani",
            todo_id=2,
            due="2026-09-11",
            priority=Priority.HIGH,
            stima_pomo=2,
        ),
        make_todo("C-domani", todo_id=3, due="2026-09-11", stima_pomo=1),
    ]
    plan = plan_day(todos, TODAY, hours=1.0)  # capacita' 2 pomodori, A ne usa 2
    assert _ids(plan) == [1, 2, 3]
    assert "plan_cut" not in _reasons(plan, 1)
    assert "plan_cut" in _reasons(plan, 2)
    assert "plan_cut" in _reasons(plan, 3)


def test_scaduti_e_oggi_mai_tagliati():
    todos = [
        make_todo("A-ritardo", todo_id=1, due="2026-09-01", stima_pomo=5),
        make_todo("B-domani", todo_id=2, due="2026-09-11"),
    ]
    plan = plan_day(todos, TODAY, hours=0)
    assert "plan_cut" not in _reasons(plan, 1)
    assert "plan_cut" in _reasons(plan, 2)
    plan = plan_day(todos, TODAY, hours="x")  # ore invalide = capacita' 0
    assert "plan_cut" not in _reasons(plan, 1)


def test_progetto_fermo():
    todos = [
        make_todo(
            "old-done",
            todo_id=1,
            project="p",
            done=True,
            completed_at="2026-09-01 10:00",
        ),
        make_todo("P-open", todo_id=2, project="p"),
        make_todo("Q-open", todo_id=3, project="q"),
        make_todo(
            "q-done", todo_id=4, project="q", done=True, completed_at="2026-09-09 10:00"
        ),
        make_todo("R-open", todo_id=5, project="r", created="2026-08-01 10:00"),
    ]
    plan = plan_day(todos, TODAY)
    for pid, _s, reasons in plan:
        keys = [k for k, _p in reasons]
        if pid == 2:
            assert ("plan_stale", {"n": 9}) in reasons
        if pid == 3:
            assert "plan_stale" not in keys
        if pid == 5:
            assert ("plan_stale", {"n": 40}) in reasons


def test_stima_mancante_vale_uno():
    todos = [
        make_todo("A", todo_id=1),
        make_todo("B", todo_id=2),
    ]
    plan = plan_day(todos, TODAY, hours=0.5)  # capacita' 1 pomo
    assert "plan_cut" not in _reasons(plan, 1)
    assert "plan_cut" in _reasons(plan, 2)


def test_vuoto_e_determinismo():
    assert plan_day([], TODAY) == []
    todos = [make_todo("B", todo_id=2), make_todo("A", todo_id=1)]
    first = plan_day(todos, TODAY)
    assert _ids(first) == [1, 2]  # pari score -> id
    assert plan_day(todos, TODAY) == first


def test_scartati_oggi_in_fondo_senza_capacita():
    todos = [
        make_todo("A", todo_id=1, due=TODAY),
        make_todo("S-skip", todo_id=2, due=TODAY, stima_pomo=50, plan_skip=TODAY),
        make_todo("B", todo_id=3, due="2026-09-11"),
    ]
    plan = plan_day(todos, TODAY, hours=1.0)
    assert _ids(plan)[-1] == 2
    assert ("plan_skipped", {}) in [r for i, _s, rs in plan for r in rs if i == 2]
    # lo scartato (stima enorme) non consuma capacita': B entra comunque
    assert "plan_cut" not in _reasons(plan, 3)


def test_skip_vecchio_riproposto():
    todos = [make_todo("S", todo_id=1, due=TODAY, plan_skip="2026-09-09")]
    plan = plan_day(todos, TODAY)
    assert len(plan) == 1
    _pid, _score, reasons = plan[0]
    assert all(k != "plan_skipped" for k, _p in reasons)


def test_roundtrip_plan_skip():
    from src.models import TodoItem

    t = make_todo("X", todo_id=1, plan_skip=TODAY)
    assert TodoItem.from_dict(t.to_dict()).plan_skip == TODAY
    t2 = make_todo("Y", todo_id=2)
    assert t2.plan_skip == ""
    assert TodoItem.from_dict(t2.to_dict()).plan_skip == ""


def test_factor_retrocompatibile_e_motivo():
    import src.plan as plan_module

    todos = [make_todo("E", todo_id=1, stima_pomo=2)]
    assert "plan_calibrated" not in _reasons(plan_day(todos, TODAY), 1)
    assert "plan_calibrated" not in _reasons(plan_day(todos, TODAY, factor="xx"), 1)
    plan = plan_day(todos, TODAY, factor=2.0)
    assert "plan_calibrated" in _reasons(plan, 1)
    [[_i, _s, reasons]] = plan
    assert ("plan_calibrated", {"f": "x2.0"}) in reasons
    # senza stima: nessun motivo anche col factor
    assert "plan_calibrated" not in _reasons(
        plan_day([make_todo("N", todo_id=2)], TODAY, factor=2.0), 2
    )
    assert plan_module._estimate(todos[0], None) == 2
    assert plan_module._estimate(todos[0], 2.0) == 4


def test_factor_capacita_calibrata():
    # 2 task da 2 stimati, capacita' 5: senza factor entrano, con x2.0 uno taglia
    todos = [
        make_todo("A", todo_id=1, stima_pomo=2),
        make_todo("B", todo_id=2, stima_pomo=2),
    ]
    assert "plan_cut" not in _reasons(plan_day(todos, TODAY, hours=2.5), 2)
    plan = plan_day(todos, TODAY, hours=2.5, factor=2.0)
    assert "plan_cut" in _reasons(plan, 1) or "plan_cut" in _reasons(plan, 2)
