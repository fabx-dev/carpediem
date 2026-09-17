"""Schermate modali. Re-export per compatibilita'.

Le classi vivono nei sottomoduli per area; questo package riesporta i nomi
pubblici cosi' `from src.screens import X` resta invariato (app, test, main).
"""

__all__ = [
    "AgendaScreen",
    "ArchiveScreen",
    "BriefingScreen",
    "CalendarScreen",
    "CloseMixin",
    "ConfirmScreen",
    "DailyPlanScreen",
    "DayScreen",
    "DetailScreen",
    "GoalsScreen",
    "HealthScreen",
    "ImportCsvScreen",
    "KanbanScreen",
    "KeysScreen",
    "LockScreen",
    "MenuRow",
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
    "SmartListScreen",
    "StateChoiceScreen",
    "StatsScreen",
    "TemplateCreateScreen",
    "TemplateProjectScreen",
    "TemplateScreen",
    "ThemeListScreen",
    "TodoFormScreen",
    "WeekScreen",
    "WelcomeScreen",
    "WorkflowScreen",
    "_hero_row",
]

from src.screens._shared import (
    CloseMixin,
    _hero_row,
)
from src.screens.form import (
    ConfirmScreen,
    NLHelpScreen,
    RadarPickScreen,
    SearchScreen,
    StateChoiceScreen,
    ThemeListScreen,
    TodoFormScreen,
)
from src.screens.menu import (
    MenuRow,
    MenuScreen,
)
from src.screens.plan import (
    BriefingScreen,
    DailyPlanScreen,
    PlanProposalScreen,
    ReviewScreen,
)
from src.screens.system import (
    ArchiveScreen,
    GoalsScreen,
    HealthScreen,
    KeysScreen,
    LockScreen,
    PasswordScreen,
    RestoreScreen,
    SecurityScreen,
    SettingsScreen,
    StatsScreen,
    WelcomeScreen,
)
from src.screens.views import (
    AgendaScreen,
    CalendarScreen,
    DayScreen,
    DetailScreen,
    ImportCsvScreen,
    KanbanScreen,
    PomodoroScreen,
    SmartListScreen,
    TemplateCreateScreen,
    TemplateProjectScreen,
    TemplateScreen,
    WeekScreen,
    WorkflowScreen,
)
