"""CarpeDiem: entry point, init lingua, re-export compatibilita."""

import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    # Esecuzione come script (python src/main.py): rende importabile il package.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from src.lang import T, resolve_lang, set_lang
except ImportError:  # esecuzione come script: python src/main.py
    from lang import (  # type: ignore[import-not-found,no-redef]
        T,
        resolve_lang,
        set_lang,
    )


def _apply_startup_lang() -> str:
    """Legge TASKO_LANG/config e imposta la lingua PRIMA delle classi (BINDINGS fissi)."""
    import os

    env = os.environ.get("TASKO_LANG", "").strip().lower()
    if env.startswith("it"):
        return set_lang("it")
    if env.startswith("en"):
        return set_lang("en")
    override = os.environ.get("TASKO_HOME", "").strip()
    base = Path(override).expanduser() if override else Path.home()
    try:
        raw = json.loads((base / ".todo_config.json").read_text(encoding="utf-8"))
        val = raw.get("lang", "auto") if isinstance(raw, dict) else "auto"
    except (OSError, ValueError):
        val = "auto"
    return set_lang(resolve_lang(val))


_apply_startup_lang()

# Import DOPO il set lingua: le classi valutano T() all'import.
from src.app import TodoApp, _demo_todos, _needs_unlock
from src.cli import _cli_main
from src.commands import CarpeDiemMenuProvider
from src.models import (
    Priority,
    Recurrence,
    TodoItem,
    _is_valid_due,
    _normalize_due,
    _pomo_label,
)
from src.screens import (
    ArchiveScreen,
    BriefingScreen,
    CalendarScreen,
    ConfirmScreen,
    DailyPlanScreen,
    DayScreen,
    DetailScreen,
    HealthScreen,
    ImportCsvScreen,
    KanbanScreen,
    KeysScreen,
    LockScreen,
    MenuScreen,
    NLHelpScreen,
    PasswordScreen,
    PlanProposalScreen,
    PomodoroScreen,
    RadarPickScreen,
    RestoreScreen,
    ReviewScreen,
    SearchScreen,
    SecurityScreen,
    SettingsScreen,
    StateChoiceScreen,
    StatsScreen,
    TemplateCreateScreen,
    TemplateProjectScreen,
    TemplateScreen,
    ThemeListScreen,
    TodoFormScreen,
    WeekScreen,
    WelcomeScreen,
)
from src.storage import (
    ARCHIVE_FILE,
    BACKUP_DIR,
    CONFIG_FILE,
    DATA_FILE,
    EXECUTIONS_FILE,
    POMODORO_FILE,
    TEMPLATE_FILE,
    _save_todos_plain,
    append_execution,
    create_backup,
    list_snapshots,
    load_archive,
    load_config,
    load_executions,
    load_pomodoro,
    load_templates,
    load_todos,
    prune_snapshots,
    restore_snapshot,
    save_archive,
    save_config,
    save_pomodoro,
    save_templates,
    snapshot_info,
)

__all__ = [
    "TodoApp",
    "TodoItem",
    "Priority",
    "Recurrence",
    "_is_valid_due",
    "_normalize_due",
    "_pomo_label",
    "_needs_unlock",
    "_demo_todos",
    "CarpeDiemMenuProvider",
    "ArchiveScreen",
    "BriefingScreen",
    "CalendarScreen",
    "ConfirmScreen",
    "DailyPlanScreen",
    "DayScreen",
    "DetailScreen",
    "HealthScreen",
    "ImportCsvScreen",
    "KanbanScreen",
    "KeysScreen",
    "LockScreen",
    "MenuScreen",
    "NLHelpScreen",
    "PasswordScreen",
    "PlanProposalScreen",
    "PomodoroScreen",
    "RadarPickScreen",
    "RestoreScreen",
    "ReviewScreen",
    "SearchScreen",
    "SecurityScreen",
    "SettingsScreen",
    "StateChoiceScreen",
    "StatsScreen",
    "TemplateCreateScreen",
    "TemplateProjectScreen",
    "TemplateScreen",
    "ThemeListScreen",
    "TodoFormScreen",
    "WeekScreen",
    "WelcomeScreen",
    "ARCHIVE_FILE",
    "BACKUP_DIR",
    "CONFIG_FILE",
    "DATA_FILE",
    "EXECUTIONS_FILE",
    "POMODORO_FILE",
    "TEMPLATE_FILE",
    "append_execution",
    "create_backup",
    "list_snapshots",
    "load_archive",
    "load_config",
    "load_executions",
    "load_pomodoro",
    "load_templates",
    "load_todos",
    "prune_snapshots",
    "restore_snapshot",
    "save_archive",
    "save_config",
    "save_pomodoro",
    "save_templates",
    "_save_todos_plain",
    "snapshot_info",
    "T",
]


def main() -> None:
    import sys

    if len(sys.argv) > 1:
        raise SystemExit(_cli_main(sys.argv[1:]))
    TodoApp().run()


if __name__ == "__main__":
    main()
