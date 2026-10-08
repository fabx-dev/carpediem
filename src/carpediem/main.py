"""CarpeDiem: entry point, init lingua, re-export compatibilita."""

import json

from carpediem.lang import T, resolve_lang, set_lang


def _apply_startup_lang() -> str:
    """Legge CARPEDIEM_LANG (poi TASKO_LANG legacy)/config e imposta la lingua.

    Va chiamata PRIMA delle classi (BINDINGS fissi). La config si legge dal
    nuovo percorso con fallback in sola lettura al legacy (la migrazione vera
    parte dopo, in main()).
    """
    import os

    for var in ("CARPEDIEM_LANG", "TASKO_LANG"):
        env = os.environ.get(var, "").strip().lower()
        if env.startswith("it"):
            return set_lang("it")
        if env.startswith("en"):
            return set_lang("en")
    from carpediem.storage import _legacy_candidate_bases, config_file

    candidates = [config_file()]
    candidates += [b / ".todo_config.json" for b in _legacy_candidate_bases()]
    val = "auto"
    for path in candidates:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                val = raw.get("lang", "auto")
                break
        except (OSError, ValueError):
            continue
    return set_lang(resolve_lang(val if isinstance(val, str) else "auto"))


_apply_startup_lang()

# Import DOPO il set lingua: le classi valutano T() all'import.
from carpediem.app import TodoApp, _demo_todos, _needs_unlock  # noqa: E402
from carpediem.cli import _cli_main  # noqa: E402
from carpediem.commands import CarpeDiemMenuProvider  # noqa: E402
from carpediem.models import (  # noqa: E402
    Priority,
    Recurrence,
    TodoItem,
    _is_valid_due,
    _normalize_due,
    _pomo_label,
)
from carpediem.screens import (  # noqa: E402
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
from carpediem.storage import (  # noqa: E402
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

    from carpediem.storage import migrate_legacy

    migrate_legacy()
    if len(sys.argv) > 1:
        raise SystemExit(_cli_main(sys.argv[1:]))
    TodoApp().run()


if __name__ == "__main__":
    main()
