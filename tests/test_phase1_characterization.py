"""Phase 1 Step 0 — test di caratterizzazione (T1/T3/T7a/T9).

Fissano il comportamento CORRENTE prima di qualunque modifica di produzione
(piano: docs/planner-phase1-plan.md, §13.2). Solo test, nessuna modifica a
src/: se un refactor futuro cambia uno di questi output, il test deve
rompersi e il cambiamento va giustificato, mai silenziato.

- T1: dual-input harness con convertitore inline TEMPORANEO nel test (Step 2
  lo sostituirà con TaskView reale): TodoItem vs mirror duck-typed con gli
  stessi valori di campo → DayPlan identici. De-rischia l'introduzione della
  projection senza toccare il core.
- T3: fallback datetime.now() caratterizzato sotto clock congelato
  (contratto compat permanente, non TODO da rimuovere in Phase 1).
- T7a (Step 4a): replan() ≡ costruzione interna con factor auto odierno;
  inventario caller + assenza di factor esplicito registrati nei commenti.
- T9: plan_day() ≡ Planner().propose().to_legacy() + layout frozen invariato
  + snapshot __all__ del boundary.
"""

import dataclasses
import sys
import types
from datetime import datetime

import src.planner.service as service_mod
from src.domain import calibration_factor
from src.models import Priority
from src.plan import plan_day
from src.planner import Planner
from src.planner.models import TimeWindow
from src.planner.replan import replan
from tests.conftest import make_todo

# NOTA shadowing: `import src.planner.replan as x` lega la FUNZIONE replan
# (attributo del package dopo gli import di __init__), non il modulo —
# usare sys.modules (lezione AGENTS.md §7, M4).
replan_mod = sys.modules["src.planner.replan"]

TODAY = "2026-09-10"
DAY = (2026, 9, 10)
FROZEN_NOW = datetime(2026, 9, 10, 15, 30)


def _win(h1, m1, h2, m2):
    return TimeWindow(datetime(*DAY, h1, m1), datetime(*DAY, h2, m2))


def _matrix():
    """Matrice scenari: merito, vincoli, capacità, mandatory, esclusioni."""
    return [
        (
            "base",
            [
                make_todo("A-ritardo", todo_id=1, due="2026-09-09"),
                make_todo("B-oggi", todo_id=2, due=TODAY, priority=Priority.HIGH),
                make_todo("C-domani", todo_id=3, due="2026-09-11"),
                make_todo("D-nodue", todo_id=4, priority=Priority.LOW),
            ],
            6.0,
        ),
        (
            "stale",
            [
                make_todo("P1", todo_id=1, project="fermo", created="2026-08-01"),
                make_todo("P2", todo_id=2, project="fermo", created="2026-08-02"),
                make_todo("Q", todo_id=3, project="attivo", created="2026-09-09"),
            ],
            6.0,
        ),
        (
            "planned-skip",
            [
                make_todo("GiaPian", todo_id=1, planned_for=TODAY),
                make_todo("Scartato", todo_id=2, plan_skip=TODAY),
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
            "esclusioni",
            [
                make_todo("Fatto", todo_id=1, due=TODAY),
                make_todo("Sospeso", todo_id=2, due=TODAY),
                make_todo("SenzaId", todo_id=None, due=TODAY),
                make_todo("Ok", todo_id=3, due=TODAY),
            ],
            6.0,
        ),
        (
            "stime-calib",
            [
                make_todo("Stimato", todo_id=1, stima_pomo=4, due=TODAY),
                make_todo("SenzaStima", todo_id=2, due=TODAY),
            ],
            6.0,
        ),
    ]


def _inline_mirror(todo):
    """Convertitore inline TEMPORANEO (solo Step 0): copia i valori di campo
    letti dal core su un namespace duck-typed. Step 1+ lo sostituisce con
    TaskView + todo_to_task(); il differenziale T1 resta identico."""
    return types.SimpleNamespace(
        id=todo.id,
        state=todo.state,
        due=todo.due,
        priority=todo.priority,
        project=todo.project,
        planned_for=todo.planned_for,
        plan_skip=todo.plan_skip,
        stima_pomo=todo.stima_pomo,
        actual_pomo=todo.actual_pomo,
        created=todo.created,
        completed_at=todo.completed_at,
        pomodoros=todo.pomodoros,
        actual_minutes=todo.actual_minutes,
        done=todo.done,
    )


def _freeze_clock(monkeypatch):
    """Congela datetime.now() nei due moduli planner che hanno il fallback."""

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(*DAY, 15, 30)

    monkeypatch.setattr(service_mod, "datetime", _Frozen)
    monkeypatch.setattr(replan_mod, "datetime", _Frozen)
    return _Frozen


# --- T1: differenziale TodoItem vs mirror ------------------------------------


def test_t1_dual_input_stesso_dayplan():
    for name, todos, hours in _matrix():
        mirrored = [_inline_mirror(t) for t in todos]
        plan_todo = Planner(todos, today=TODAY, hours=hours).propose()
        plan_mirror = Planner(mirrored, today=TODAY, hours=hours).propose()
        assert plan_mirror == plan_todo, f"scenario {name}"
        assert plan_mirror.to_legacy() == plan_todo.to_legacy(), f"scenario {name}"


def test_t1_esclusioni_invisibili_anche_via_mirror():
    todos = [
        make_todo("Fatto", todo_id=1, due=TODAY),
        make_todo("Sospeso", todo_id=2, due=TODAY),
        make_todo("SenzaId", todo_id=None, due=TODAY),
        make_todo("Ok", todo_id=3, due=TODAY),
    ]
    todos[0].done = True
    todos[1].paused = True
    mirrored = [_inline_mirror(t) for t in todos]
    ids = {
        it.todo_id for it in Planner(mirrored, today=TODAY, hours=6.0).propose().items
    }
    assert ids == {3}, ids  # completato/sospeso/id-None non compaiono mai


def test_input_normalizzato_forma_e_coerenza():
    """Step 5: _normalize() e' la sola via di risoluzione input — giorno,
    viste TaskView, capacita', factor coerenti con propose()."""
    from src.planner.models import TaskView

    todos = [
        make_todo("A", todo_id=1, due=TODAY, stima_pomo=2),
        make_todo("B", todo_id=2),
    ]
    planner = Planner(todos, today=TODAY, hours=4.0)
    inp = planner._normalize()
    assert str(inp.day) == TODAY and inp.today_s == TODAY
    assert inp.capacity_pomo == 8.0
    assert inp.factor is None  # senza storia: nessuna calibrazione
    assert all(isinstance(v, TaskView) for v in inp.views)
    assert [v.id for v in inp.views] == [1, 2]
    plan = planner.propose()
    assert plan.capacity_pomo == inp.capacity_pomo
    assert plan.factor == inp.factor
    assert str(plan.day) == inp.today_s


# --- T3: fallback wall-clock caratterizzato ----------------------------------


def test_t3_propose_fallback_uguale_a_esplicito(monkeypatch):
    _freeze_clock(monkeypatch)
    for name, todos, hours in _matrix():
        fallback = Planner(todos, hours=hours).propose()
        explicit = Planner(todos, today=TODAY, hours=hours).propose()
        assert fallback == explicit, f"scenario {name}"
        assert str(fallback.day) == TODAY, f"scenario {name}"


def test_t3_replan_fallback_uguale_a_esplicito(monkeypatch):
    _freeze_clock(monkeypatch)
    todos = [
        make_todo("A", todo_id=1, planned_for=TODAY, stima_pomo=2),
        make_todo("B", todo_id=2, stima_pomo=2),
    ]
    avail = [_win(9, 0, 18, 0)]
    via_fallback = replan(todos, TODAY, 6.0, avail, (), None)
    via_explicit = replan(todos, TODAY, 6.0, avail, (), FROZEN_NOW)
    assert via_fallback == via_explicit
    assert via_fallback.now == FROZEN_NOW


def test_t3_explicit_today_vince_sul_clock(monkeypatch):
    """Regressione cross-midnight: today esplicito guida, mai l'orologio."""
    _freeze_clock(monkeypatch)  # clock fermo al 2026-09-10 15:30
    todos = [make_todo("Scad", todo_id=1, due="2026-09-10")]
    plan = Planner(todos, today="2026-09-12", hours=6.0).propose()
    assert str(plan.day) == "2026-09-12"
    assert any(k == "plan_overdue" for _r in plan.to_legacy() for k, _p in _r[2]), (
        plan.to_legacy()
    )


# --- T7a (Step 4a): replan factor corrente -----------------------------------
#
# Inventario production caller di replan() (verificato 2026-09-30):
#   1. ReplanPreviewScreen._proposal (src/screens/plan.py:1170-1178)
#   2. CLI _cli_replan (src/cli.py:91)
# Nessuno dei due passa né detiene un factor esplicito: tutti i call-site
# Planner(...  ) omettono factor= (auto path); l'unico `factor=` in produzione
# (screens/plan.py:241) è read-out (plan.factor → DayPlan re-wrap), mai
# injection. Quindi il path interno di replan() è sempre auto-calibrazione
# sullo stesso todo list — caratterizzato qui, prima di qualunque seam.


def test_t7a_replan_usa_factor_auto_interno():
    for name, todos, hours in _matrix():
        avail = [_win(9, 0, 18, 0)]
        proposal = replan(todos, TODAY, hours, avail, (), FROZEN_NOW)
        plan = Planner(todos, today=TODAY, hours=hours).propose()
        assert proposal.day == plan.day, f"scenario {name}"
        assert proposal.capacity_pomo == plan.capacity_pomo, f"scenario {name}"
        assert proposal.planned_pomo == plan.planned_pomo, f"scenario {name}"
        assert plan.factor == calibration_factor(todos), f"scenario {name}"
        new_ids = {it.todo_id for it in plan.planned}
        moved_ids = {
            m.todo_id for m in proposal.moves if m.kind in ("kept", "moved", "added")
        }
        current_ids = {
            t.id
            for t in todos
            if getattr(t, "state", None) == "attivo"
            and getattr(t, "planned_for", "") == TODAY
            and t.id is not None
        }
        assert moved_ids <= (new_ids | current_ids), f"scenario {name}"


def test_t7a_replan_condivide_factor_auto_calibrato():
    """Step 4a, caso forte: con dati di calibrazione (factor attivo, non
    None) il replan interno usa ESATTAMENTE l'auto-factor del chiamante.

    6 completati (stima 2, actual 4) -> factor 2.0; gli attivi raddoppiano
    la stima consumata. Prova auto≡auto a calibrazione viva, prima del seam.
    """
    todos = [
        make_todo(f"C{i}", todo_id=100 + i, stima_pomo=2, actual_pomo=4)
        for i in range(6)
    ]
    for t in todos:
        t.done = True
    todos += [
        make_todo("A", todo_id=1, planned_for=TODAY, stima_pomo=2),
        make_todo("B", todo_id=2, stima_pomo=1),
        make_todo("C", todo_id=3, stima_pomo=3),
    ]
    auto = calibration_factor(todos)
    assert auto == 2.0  # precondizione: calibrazione viva
    avail = [_win(9, 0, 18, 0)]
    proposal = replan(todos, TODAY, 6.0, avail, (), FROZEN_NOW)
    plan_auto = Planner(todos, today=TODAY, hours=6.0).propose()
    plan_explicit = Planner(todos, today=TODAY, hours=6.0, factor=auto).propose()
    assert plan_auto.factor == 2.0
    assert plan_auto == plan_explicit  # auto ≡ esplicito sullo stesso input
    assert proposal.planned_pomo == plan_auto.planned_pomo
    assert proposal.capacity_pomo == plan_auto.capacity_pomo
    # Le mosse coprono current ∪ planned: i kept/moved/added sono ESATTAMENTE
    # i planned del motore interno (nessun secondo scoring nel replan).
    assert {it.todo_id for it in plan_auto.planned} == {
        m.todo_id for m in proposal.moves if m.kind in ("kept", "moved", "added")
    }
    # Le stime consumate sono calibrate (2 -> 4): A da solo riempie 4 pomo.
    by_id = {it.todo_id: it for it in plan_auto.planned}
    assert by_id[1].estimate_pomo == 4
    assert any(k == "plan_calibrated" for k, _p in by_id[1].reasons)


def _calibrated_scenario():
    """6 completati (stima 2, actual 4) + 3 attivi: factor auto 2.0 vivo."""
    todos = [
        make_todo(f"C{i}", todo_id=100 + i, stima_pomo=2, actual_pomo=4)
        for i in range(6)
    ]
    for t in todos:
        t.done = True
    todos += [
        make_todo("A", todo_id=1, planned_for=TODAY, stima_pomo=2),
        make_todo("B", todo_id=2, stima_pomo=1),
        make_todo("C", todo_id=3, stima_pomo=3),
    ]
    assert calibration_factor(todos) == 2.0
    return todos


def test_t7b_replan_factor_default_uguale_a_omesso():
    """Step 4b: factor=None esplicito riproduce T7a (default invariato)."""
    todos = _calibrated_scenario()
    avail = [_win(9, 0, 18, 0)]
    assert replan(todos, TODAY, 6.0, avail, (), FROZEN_NOW, factor=None) == replan(
        todos, TODAY, 6.0, avail, (), FROZEN_NOW
    )


def test_t7b_replan_factor_esplicito_uguale_a_costruzione_manuale():
    """Step 4b: il seam inietta davvero — factor=1.0 dimezza le stime e la
    proposta coincide con Planner(factor=1.0) + schedule costruiti a mano."""
    todos = _calibrated_scenario()
    avail = [_win(9, 0, 18, 0)]
    default = replan(todos, TODAY, 6.0, avail, (), FROZEN_NOW)
    explicit = replan(todos, TODAY, 6.0, avail, (), FROZEN_NOW, factor=1.0)
    assert explicit != default  # il seam ha effetto osservabile
    assert explicit.planned_pomo < default.planned_pomo
    manual = Planner(todos, today=TODAY, hours=6.0, factor=1.0).propose()
    assert explicit.planned_pomo == manual.planned_pomo
    assert explicit.capacity_pomo == manual.capacity_pomo
    # Stessi planned del motore con factor iniettato (nessuna selezione bis).
    assert {it.todo_id for it in manual.planned} == {
        m.todo_id for m in explicit.moves if m.kind in ("kept", "moved", "added")
    }
    # A dimezzato (2 -> 2/1.0… base 2, factor 1.0): stima consumata 2, non 4.
    by_id = {it.todo_id: it for it in manual.planned}
    assert by_id[1].estimate_pomo == 2


# --- T9: compat wrapper + layout frozen --------------------------------------


def test_t9_plan_day_uguale_a_propose_to_legacy():
    for name, todos, hours in _matrix():
        assert (
            plan_day(todos, today=TODAY, hours=hours)
            == Planner(todos, today=TODAY, hours=hours).propose().to_legacy()
        ), f"scenario {name}"


def test_t9_layout_modelli_frozen_invariato():
    import src.planner.models as m

    assert [f.name for f in dataclasses.fields(m.PlanItem)] == [
        "todo_id",
        "score",
        "reasons",
        "estimate_pomo",
        "mandatory",
    ]
    assert [f.name for f in dataclasses.fields(m.DayPlan)] == [
        "day",
        "planned",
        "cut",
        "skipped",
        "capacity_pomo",
        "planned_pomo",
        "factor",
    ]
    assert [f.name for f in dataclasses.fields(m.ScheduledDayPlan)] == [
        "plan",
        "scheduled",
        "unscheduled",
        "availability",
        "busy",
    ]
    assert [f.name for f in dataclasses.fields(m.ScheduledItem)] == [
        "item",
        "start",
        "end",
    ]
    assert [f.name for f in dataclasses.fields(m.TimeWindow)] == ["start", "end"]
    assert [f.name for f in dataclasses.fields(m.FixedEvent)] == [
        "title",
        "start",
        "end",
    ]
    assert [f.name for f in dataclasses.fields(m.ExecutionFeedback)] == [
        "todo_id",
        "estimate_pomo",
        "estimate_minutes",
        "scheduled_start",
        "scheduled_end",
        "sessions",
        "actual_pomo",
        "actual_minutes",
        "completed",
        # B1: campo additivo in coda con default (policy api §4, no bump).
        "raw_estimate_pomo",
    ]
    assert [f.name for f in dataclasses.fields(replan_mod.ReplanProposal)] == [
        "day",
        "now",
        "moves",
        "capacity_pomo",
        "planned_pomo",
        "residual_pomo",
        # F4: campo additivo in coda con default (policy api §4, no bump).
        "remaining_min",
    ]
    assert [f.name for f in dataclasses.fields(replan_mod.ReplanMove)] == [
        "todo_id",
        "kind",
        "old_start",
        "old_end",
        "new_start",
        "new_end",
        "reasons",
        "primary",
    ]


def test_t9_export_boundary_invariati():
    import src.planner as p

    assert set(p.__all__) == {
        "ADDED",
        "BLOCKED_BUSY",
        "BLOCKED_CAPACITY",
        "BLOCKED_DEADLINE",
        "BLOCKED_DURATION",
        "BLOCKED_KINDS",
        "BLOCKED_TASKS",
        "BLOCKED_USER_SKIP",
        "BLOCKED_WINDOW",
        "CONSTRAINED",
        "DEFERRED",
        "DETAIL_KEYS",
        "DIAG_CONSTRAINED",
        "DIAG_KINDS",
        "DIAG_NO_AVAIL",
        "DIAG_OVERFLOW",
        "DROPPED",
        "DayPlan",
        "ExecutionFeedback",
        "FixedEvent",
        "KEPT",
        "MOVED",
        "NOT_SCHEDULED",
        "PLANNER_CONTRACT_VERSION",  # Phase 7 P7-1: unico nome aggiunto, deliberato
        "PlanAlternative",
        "PlanDiagnostic",
        "PlanItem",
        "Planner",
        "PlanningDecision",
        "PlanningRequest",
        "PlanningResult",
        "ReplanMove",
        "ReplanProposal",
        "SCHEDULED",
        "ScheduledDayPlan",
        "ScheduledItem",
        "TaskView",
        "TimeWindow",
        "decide",
        "deadlines_for",
        "diagnose",
        "events_to_busy",
        "explain_decision",
        "explain_proposed",
        "factor_for",
        "feedback",
        "observe",
        "observe_all",
        "plan",
        "primary_reason",
        "refine_with_schedule",
        "replan",
        "schedule",
        "story_keys",
        "todo_to_task",
    }
