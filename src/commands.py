"""Provider comandi per menu/palette + struttura categorie del menu m."""

from textual.command import DiscoveryHit, Hit, Provider

from src.lang import T

# Struttura del menu per funzioni: chiavi i18n (risolte a runtime) +
# nome action di TodoApp + scorciatoia mostrata tra parentesi (o None).
# (chiave titolo cat, chiave aiuto cat, ((chiave titolo, chiave aiuto, action, shortcut), ...))
MENU_STRUCTURE: tuple = (
    (
        "menu_cat_day_t",
        "menu_cat_day_h",
        (
            ("menu_workflow_t", "menu_workflow_h", "action_view_workflow", None),
            ("menu_morning_t", "menu_morning_h", "action_plan_day", "P"),
            ("menu_agenda_t", "menu_agenda_h", "action_view_agenda", None),
            ("menu_dayplan_t", "menu_dayplan_h", "action_view_daily_plan", "p"),
            ("menu_week_t", "menu_week_h", "action_view_week", "w"),
            ("menu_weekreview_t", "menu_weekreview_h", "action_view_week_review", "W"),
            ("menu_cal_t", "menu_cal_h", "action_view_calendar", "c"),
            ("menu_retro_t", "menu_retro_h", "action_briefing_evening", None),
            ("menu_review_t", "menu_review_h", "action_open_review", "R"),
            ("menu_replan_t", "menu_replan_h", "action_view_replan", "G"),
        ),
    ),
    (
        "menu_cat_views_t",
        "menu_cat_views_h",
        (
            ("menu_kbmini_t", "menu_kbmini_h", "action_toggle_kanban", "b"),
            ("menu_kbfull_t", "menu_kbfull_h", "action_view_kanban", "B"),
            ("menu_stats_t", "menu_stats_h", "action_view_stats", "k"),
            ("menu_smart_t", "menu_smart_h", "action_open_smart_lists", None),
            ("menu_health_t", "menu_health_h", "action_view_health", "y"),
            ("menu_tpl_t", "menu_tpl_h", "action_new_from_template", "T"),
            ("menu_goals_t", "menu_goals_h", "action_edit_goals", None),
        ),
    ),
    (
        "menu_cat_data_t",
        "menu_cat_data_h",
        (
            ("menu_backup_now_t", "menu_backup_now_h", "action_backup_now", None),
            (
                "menu_backup_restore_t",
                "menu_backup_restore_h",
                "action_restore_backup",
                None,
            ),
            ("menu_exp_md_t", "menu_exp_md_h", "action_export_data", "ctrl+e"),
            ("menu_exp_csv_t", "menu_exp_csv_h", "action_export_csv", None),
            ("menu_exp_stats_t", "menu_exp_stats_h", "action_export_stats_csv", None),
            ("menu_exp_ical_t", "menu_exp_ical_h", "action_export_ical", None),
            ("menu_imp_csv_t", "menu_imp_csv_h", "action_import_csv", None),
            ("menu_archive_do_t", "menu_archive_do_h", "action_archive_done", None),
            ("menu_archive_view_t", "menu_archive_view_h", "action_view_archive", None),
        ),
    ),
    (
        "menu_cat_sys_t",
        "menu_cat_sys_h",
        (
            ("menu_settings_t", "menu_settings_h", "action_open_settings", None),
            ("menu_security_t", "menu_security_h", "action_open_security", None),
            ("menu_clearf_t", "menu_clearf_h", "action_clear_filters", "C"),
            ("menu_theme_t", "menu_theme_h", "action_choose_theme", "v"),
            ("menu_keys_t", "menu_keys_h", "action_show_keys", None),
            ("menu_snap_t", "menu_snap_h", "action_save_screenshot", "ctrl+s"),
            ("menu_refresh_t", "menu_refresh_h", "action_refresh", "r"),
            ("menu_quit_t", "menu_quit_h", "action_quit", "q"),
        ),
    ),
)

# Compatibilita': vecchia lista piatta valutata all'import (test storici).
MENU_IT: tuple[tuple[str, str, str], ...] = tuple(
    (T(tk), T(hk), action)
    for _ck, _ch, _items in MENU_STRUCTURE
    for tk, hk, action, _sc in _items
)


def menu_categories() -> list[tuple[str, str, list[tuple[str, str, str, str | None]]]]:
    """Categorie con stringhe risolte nella lingua corrente.

    Ritorna [(titolo_cat, aiuto_cat, [(titolo, aiuto, action, shortcut), ...]), ...].
    """
    out = []
    for cat_tk, cat_hk, items in MENU_STRUCTURE:
        out.append(
            (
                T(cat_tk),
                T(cat_hk),
                [(T(tk), T(hk), action, sc) for tk, hk, action, sc in items],
            )
        )
    return out


def _display(cat: str, title: str, shortcut: str | None) -> str:
    base = f"{cat} › {title}"
    return f"{base} ({shortcut})" if shortcut else base


class CarpeDiemMenuProvider(Provider):
    """Voci del menu per la palette (ctrl+p): piatte ma prefissate per categoria."""

    # Compatibilita' storica: vecchia lista piatta (test e import esterni).
    MENU_IT: tuple[tuple[str, str, str], ...] = MENU_IT

    def _iter(self):
        for cat_title, _cat_help, items in menu_categories():
            for title, help_text, action_name, shortcut in items:
                callback = getattr(self.app, action_name, None)
                if callable(callback):
                    yield _display(cat_title, title, shortcut), help_text, callback

    async def discover(self):
        for title, help_text, callback in self._iter():
            yield DiscoveryHit(title, callback, help=help_text)

    async def search(self, query: str):
        matcher = self.matcher(query)
        for title, help_text, callback in self._iter():
            if (match := matcher.match(title)) > 0:
                yield Hit(match, matcher.highlight(title), callback, help=help_text)
