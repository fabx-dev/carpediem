"""Guardrail Fase 9: la UI e' consumer del Planner, mai secondo planner.

Non vieta ordinamenti/filtri di presentazione (legittimi in review/agenda):
vieta la duplicazione di merito/capacita'/scheduling e il percorso legacy.
Nessun vincolo su QUALI screen possano usare il Planner: oggi PlanProposalScreen
e' il consumer ufficiale (Fasi 6.5/7), domani altre screen potranno esserlo —
purché attraverso il boundary src/planner, non reimplementandolo.
"""

import pathlib
import re

UI_FILES = sorted(pathlib.Path("src/screens").glob("*.py")) + [
    pathlib.Path("src/app.py")
]

# Costanti di merito/capacita': se una screen le usa, sta ricalcolando il merito.
WEIGHT_CONSTANTS = (
    "OVERDUE_SCORE",
    "DUE_TODAY_SCORE",
    "DUE_TOMORROW_SCORE",
    "PRIO_SCORES",
    "STALE_SCORE",
    "STALE_DAYS",
    "PLANNED_SCORE",
    "POMO_HOURS",
    "DEFAULT_ESTIMATE",
)

# Reimplementazione del boundary: definizioni locali di propose/schedule/Planner.
REIMPLEMENTATION = ("def propose(", "def schedule(", "class Planner", "def plan_day(")

# M2 TaskExecution: la UI consuma dati pronti, mai li costruisce o ricalcola.
# Le screen ricevono callback opache (es. on_completed); solo app.py puo'
# orchestrare il recorder sottile (make/resolve/append), mai le statistiche.
SCREEN_FORBIDDEN = (
    "make_execution",
    "append_execution",
    "load_executions",
    "execution_stats",
    "execution_confidence",
    "predicted_minutes",
    "calibration_summary",
    "resolve_actual_minutes",
    "resolve_planned_minutes",
)

# app.py puo' chiamare il recorder, ma non ricalcolare stats/calibration.
APP_FORBIDDEN = (
    "execution_stats",
    "execution_confidence",
    "predicted_minutes",
    "calibration_summary",
)

FAIL_MSG = "La UI e' consumer del Planner (Fase 9): niente merito/capacita'/scheduling duplicati; usa src/planner, non plan_day()."
FAIL_EXEC_MSG = "M2: la UI consuma execution/stats/calibration pronte, non le costruisce (dominio/planner la fonte)."


def _sources():
    return [(p, p.read_text(encoding="utf-8")) for p in UI_FILES]


def _screen_sources():
    return [(p, s) for p, s in _sources() if "screens" in p.parts]


def test_no_costanti_merito_nella_ui():
    for path, src in _sources():
        for const in WEIGHT_CONSTANTS:
            assert const not in src, f"{path}: costante {const} nella UI. {FAIL_MSG}"


def test_no_reimplementazione_planner_nelle_screen():
    for path, src in _sources():
        for pat in REIMPLEMENTATION:
            assert pat not in src, f"{path}: '{pat}' duplica il boundary. {FAIL_MSG}"


# "src.plan" ma non "src.planner"; "plan_day(" come chiamata, non come
# suffisso di un identificatore (es. action_plan_day e' wiring, non planning).
_LEGACY_PLAN = re.compile(r"src\.plan(?!ner)")
_PLAN_DAY_CALL = re.compile(r"(?<![\w])plan_day\(")


def test_no_plan_day_legacy_nella_produzione_ui():
    for path, src in _sources():
        assert not _PLAN_DAY_CALL.search(src), (
            f"{path}: usa il Planner, non plan_day(). {FAIL_MSG}"
        )
        assert not _LEGACY_PLAN.search(src), (
            f"{path}: legacy src/plan vietato dalla Fase 9. {FAIL_MSG}"
        )


def test_no_execution_logic_nelle_screen():
    for path, src in _screen_sources():
        for name in SCREEN_FORBIDDEN:
            assert name not in src, f"{path}: '{name}' nella screen. {FAIL_EXEC_MSG}"


def test_no_execution_stats_in_app():
    src = pathlib.Path("src/app.py").read_text(encoding="utf-8")
    for name in APP_FORBIDDEN:
        assert name not in src, f"src/app.py: '{name}' nell'app. {FAIL_EXEC_MSG}"
