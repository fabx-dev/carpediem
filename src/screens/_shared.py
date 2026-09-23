"""Helper condivisi delle screen + CloseMixin. Dipendono solo da models/storage/lang/nlparse/plan/domain (+ _shared). Mai app."""

import re
from datetime import datetime, timedelta

from textual.screen import ModalScreen

from src.lang import T
from src.models import (
    TodoItem,
    _due_date_part,
    _due_time_part,
)


def _parse_day(due: str):
    part = _due_date_part(due)
    if not part:
        return datetime.max.date()
    try:
        return datetime.strptime(part, "%Y-%m-%d").date()
    except ValueError:
        return datetime.max.date()


def _agenda_due(todo: TodoItem) -> str:
    day = _due_date_part(todo.due)
    if not day:
        return ""
    try:
        d = datetime.strptime(day, "%Y-%m-%d").date()
        label = f"{d.day:02d}/{d.month:02d}"
    except ValueError:
        label = day
    time = _due_time_part(todo.due)
    return f"({label} {time}) " if time else f"({label}) "


_RICH_STYLE_TAGS = (
    "b",
    "/b",
    "dim",
    "/dim",
    "green",
    "red",
    "cyan",
    "yellow",
    "bold",
    "/bold",
    "italic",
    "/italic",
    "underline",
    "/underline",
)


def _strip_rich_tags(line: str) -> str:
    """Toglie i tag di stile noti (il resto, es. [x] utente, resta intatto)."""
    tags = "|".join(re.escape(t) for t in _RICH_STYLE_TAGS)
    return re.sub(rf"\[({tags})\]", "", line).strip()


def _escape_markup(text: str) -> str:
    """Rende letterali le parentesi quadre (i widget le leggono come Rich)."""
    return text.replace("[", "\\[")


_OUTLOOK_ERROR_KEYS = {
    "need_lock": "n_outlook_need_lock",
    "network": "outlook_err_network",
    "unauthorized": "outlook_err_unauthorized",
    "admin_consent": "outlook_err_admin",
    "account_mismatch": "outlook_err_account",
    "bad_form": "outlook_bad_form",
    "msal_missing": "outlook_err_msal",
}


def outlook_error_text(code: str, detail: str = "") -> str:
    """Messaggio UI per un codice OutlookError (condiviso dalle screen).

    Le screen non importano mai outlook_auth (rete): i callback di app
    ritornano dict con `code`, qui solo mapping a stringhe i18n.
    """
    key = _OUTLOOK_ERROR_KEYS.get(code or "")
    if key is None:
        return T("outlook_err_generic", e=detail or code or "—")
    if key == "n_outlook_need_lock":
        return T(key)
    return T(key)


def _hero_row(label: str, value: str) -> str:
    """Riga statistica allineata: label puntinata a larghezza fissa."""
    dots = "." * max(2, 16 - len(label))
    return f"  {label} {dots} {value}"


def _done_on_day(todos: list[TodoItem], day: str) -> list[TodoItem]:
    return [t for t in todos if t.done and (t.completed_at or "")[:10] == day]


def _pomo_on_day(todos: list[TodoItem], day: str) -> int:
    return sum(1 for t in todos for ts in (t.pomodoro_log or []) if ts[:10] == day)


def _streak_days(by_date: dict[str, int], today: str) -> int:
    """Serie di giorni di fila con completati (vale da ieri se oggi e' a zero)."""
    try:
        today_d = datetime.strptime(today, "%Y-%m-%d").date()
    except ValueError:
        return 0
    d = (
        today_d
        if by_date.get(today_d.strftime("%Y-%m-%d"), 0) > 0
        else today_d - timedelta(days=1)
    )
    streak = 0
    while by_date.get(d.strftime("%Y-%m-%d"), 0) > 0:
        streak += 1
        d -= timedelta(days=1)
    return streak


def _completed_by_date(todos: list[TodoItem]) -> dict[str, int]:
    """Completati per giorno (chiave YYYY-MM-DD)."""
    result: dict[str, int] = {}
    for t in todos:
        if t.completed_at:
            day = t.completed_at[:10]
            result[day] = result.get(day, 0) + 1
    return result


def _pomodoros_by_date(todos: list[TodoItem]) -> dict[str, int]:
    """Pomodori per giorno (chiave YYYY-MM-DD)."""
    result: dict[str, int] = {}
    for t in todos:
        for ts in getattr(t, "pomodoro_log", []) or []:
            day = str(ts)[:10]
            result[day] = result.get(day, 0) + 1
    return result


class CloseMixin(ModalScreen):
    """Chiusura via escape condivisa (le screen tengono i propri BINDINGS)."""

    def action_close(self) -> None:
        self.dismiss()
