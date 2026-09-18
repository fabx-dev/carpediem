"""Modello dati: task, priorita, ricorrenze, validazioni, label."""

import calendar
from datetime import datetime, timedelta
from enum import Enum

from src.lang import format_date_long

MAX_DEPTH = 6

# Nomi giorni/mesi localizzati: vedi lang.months(), lang.days_short(),
# lang.days_long(), lang.format_date_long().


def _format_date_it(date_str: str) -> str:
    """Compat: formattazione data lunga localizzata."""
    return format_date_long(date_str)


PRIORITY_ORDER = {"alta": 0, "media": 1, "bassa": 2}


def _is_valid_date(value: str) -> bool:
    if not value:
        return True
    return _is_valid_due(value)


def _due_date_part(due: str) -> str:
    """Ritorna solo la parte YYYY-MM-DD di un due che può avere HH:MM."""
    if not due:
        return ""
    return due.strip().split()[0]


def _due_time_part(due: str) -> str:
    parts = (due or "").strip().split()
    if len(parts) >= 2 and len(parts[1]) == 5 and parts[1][2] == ":":
        return parts[1]
    return ""


def _is_valid_due(value: str) -> bool:
    if not value:
        return True
    v = value.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            datetime.strptime(v, fmt)
            return True
        except ValueError:
            continue
    return False


def _normalize_date(value: str) -> str:
    return _normalize_due(value)


def _normalize_due(value: str) -> str:
    if not value:
        return ""
    v = value.strip().lower()
    today = datetime.now().date()
    if v in ("oggi", "today"):
        return today.strftime("%Y-%m-%d")
    if v in ("domani", "tomorrow"):
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")
    # Separa eventuale orario HH:MM
    time_part = ""
    date_part = value.strip()
    m = None
    import re as _re

    m = _re.search(r"(\d{1,2}:\d{2})\s*$", date_part)
    if m:
        time_part = m.group(1)
        # valida orario
        try:
            datetime.strptime(time_part, "%H:%M")
        except ValueError:
            return value.strip()
        date_part = date_part[: m.start()].strip()
        if len(time_part) == 4:  # es. 9:00 -> 09:00
            time_part = f"0{time_part}"
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            d = datetime.strptime(date_part, fmt).date().strftime("%Y-%m-%d")
            return f"{d} {time_part}" if time_part else d
        except ValueError:
            continue
    return value.strip()


class Priority(str, Enum):
    HIGH = "alta"
    MEDIUM = "media"
    LOW = "bassa"

    @property
    def color(self) -> str:
        return {
            Priority.HIGH: "red",
            Priority.MEDIUM: "yellow",
            Priority.LOW: "green",
        }[self]


class Recurrence(str, Enum):
    NONE = "nessuna"
    DAILY = "giornaliero"
    WEEKLY = "settimanale"
    MONTHLY = "mensile"
    YEARLY = "annuale"

    def next_date(self, current_date: str) -> str:
        if not current_date:
            return ""
        # Preserva eventuale orario HH:MM
        time_part = _due_time_part(current_date)
        date_part = _due_date_part(current_date)
        try:
            date = datetime.strptime(date_part, "%Y-%m-%d").date()
        except ValueError:
            return current_date
        if self == Recurrence.DAILY:
            out = (date + timedelta(days=1)).strftime("%Y-%m-%d")
        elif self == Recurrence.WEEKLY:
            out = (date + timedelta(weeks=1)).strftime("%Y-%m-%d")
        elif self == Recurrence.MONTHLY:
            month = date.month + 1
            year = date.year
            if month > 12:
                month = 1
                year += 1
            last_day = calendar.monthrange(year, month)[1]
            out = f"{year}-{month:02d}-{min(date.day, last_day):02d}"
        elif self == Recurrence.YEARLY:
            try:
                out = date.replace(year=date.year + 1).strftime("%Y-%m-%d")
            except ValueError:
                # 29 feb -> 28 feb negli anni non bisestili
                out = date.replace(year=date.year + 1, day=28).strftime("%Y-%m-%d")
        else:
            return current_date
        return f"{out} {time_part}" if time_part else out


class TodoItem:
    def __init__(
        self,
        title: str,
        priority: Priority = Priority.MEDIUM,
        done: bool = False,
        paused: bool = False,
        created: str = "",
        due: str = "",
        notes: str = "",
        parent_id: int | None = None,
        todo_id: int | None = None,
        recurrence: Recurrence = Recurrence.NONE,
        tags: list[str] | None = None,
        planned_for: str = "",
        completed_at: str = "",
        project: str = "",
        pomodoros: int = 0,
        pomodoro_log: list[str] | None = None,
        stima_pomo: int = 0,
        plan_skip: str = "",
        actual_pomo: int = 0,
        actual_minutes: int = 0,
        source: str = "",
        external_id: str = "",
    ):
        self.id = todo_id
        self.title = title
        self.priority = priority
        self.done = done
        self.paused = paused
        self.created = str(created or "")
        self.due = due
        self.notes = notes
        self.parent_id = parent_id
        self.recurrence = recurrence
        self.tags = tags or []
        self.planned_for = planned_for
        self.completed_at = completed_at
        self.project = (project or "").strip().lower()
        try:
            self.pomodoros = int(pomodoros or 0)
        except (ValueError, TypeError):
            self.pomodoros = 0
        try:
            self.stima_pomo = max(0, int(stima_pomo or 0))
        except (ValueError, TypeError):
            self.stima_pomo = 0
        # Tempo effettivo a completamento (pomodori + minuti reali).
        # Indipendente da pomodoros/stima: file vecchi -> 0, mai sovrascritto
        # dalla calibrazione (la calibrata resta solo display in plan_day).
        try:
            self.actual_pomo = max(0, int(actual_pomo or 0))
        except (ValueError, TypeError):
            self.actual_pomo = 0
        try:
            self.actual_minutes = max(0, int(actual_minutes or 0))
        except (ValueError, TypeError):
            self.actual_minutes = 0
        # Identita' esterna (Fase 8, import): (source, external_id) identifica
        # il record nella sorgente senza toccare l'id interno. File vecchi e
        # task locali -> "" (nessuna identita' esterna, mai dedup euristico).
        self.source = str(source or "").strip().lower()
        self.external_id = str(external_id or "").strip()
        # Giorno YYYY-MM-DD in cui il task e' stato scartato dal piano smart
        # (proposta successiva lo mostra deselezionato; si azzera al cambio giorno).
        self.plan_skip = str(plan_skip or "")
        # Log timestamp dei pomodori completati ("YYYY-MM-DD HH:MM"), per i trend.
        # I task vecchi non ce l'hanno: resta [] e il totale resta in pomodoros.
        if isinstance(pomodoro_log, list):
            self.pomodoro_log = [
                str(x)[:16] for x in pomodoro_log if isinstance(x, str) and x.strip()
            ]
        else:
            self.pomodoro_log = []

    @property
    def is_subtask(self) -> bool:
        return self.parent_id is not None

    @property
    def state(self) -> str:
        if self.done:
            return "completato"
        if self.paused:
            return "in_sospeso"
        return "attivo"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "priority": self.priority.value,
            "done": self.done,
            "paused": self.paused,
            "created": self.created,
            "due": self.due,
            "notes": self.notes,
            "parent_id": self.parent_id,
            "recurrence": self.recurrence.value,
            "tags": self.tags,
            "planned_for": self.planned_for,
            "completed_at": self.completed_at,
            "project": self.project,
            "pomodoros": self.pomodoros,
            "pomodoro_log": self.pomodoro_log,
            "stima_pomo": self.stima_pomo,
            "plan_skip": self.plan_skip,
            "actual_pomo": self.actual_pomo,
            "actual_minutes": self.actual_minutes,
            "source": self.source,
            "external_id": self.external_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TodoItem":
        try:
            priority = Priority(data.get("priority", "media"))
        except ValueError:
            priority = Priority.MEDIUM
        try:
            recurrence = Recurrence(data.get("recurrence", "nessuna"))
        except ValueError:
            recurrence = Recurrence.NONE
        raw_tags = data.get("tags", [])
        tags = (
            [
                str(t).strip().lower()
                for t in raw_tags
                if isinstance(t, str) and t.strip()
            ]
            if isinstance(raw_tags, list)
            else []
        )
        try:
            parent_id = (
                int(data["parent_id"]) if data.get("parent_id") is not None else None
            )
        except (ValueError, TypeError):
            parent_id = None
        try:
            todo_id = int(data["id"]) if data.get("id") is not None else None
        except (ValueError, TypeError):
            todo_id = None
        return cls(
            todo_id=todo_id,
            title=str(data.get("title") or "Senza titolo"),
            priority=priority,
            done=bool(data.get("done", False)),
            paused=bool(data.get("paused", False)),
            created=str(data.get("created", "")),
            due=_normalize_date(str(data.get("due", "") or "")),
            notes=str(data.get("notes", "") or ""),
            parent_id=parent_id,
            recurrence=recurrence,
            tags=tags,
            planned_for=str(data.get("planned_for", "") or ""),
            completed_at=str(data.get("completed_at", "") or ""),
            project=str(data.get("project", "") or ""),
            pomodoros=data.get("pomodoros", 0),
            pomodoro_log=data.get("pomodoro_log", []),
            stima_pomo=data.get("stima_pomo", 0),
            plan_skip=str(data.get("plan_skip", "") or ""),
            actual_pomo=data.get("actual_pomo", 0),
            actual_minutes=data.get("actual_minutes", 0),
            source=data.get("source", ""),
            external_id=data.get("external_id", ""),
        )


def _status(t: TodoItem) -> str:
    if t.done:
        return "[green]X[/green]"
    if t.paused:
        return "[yellow]P[/yellow]"
    return "[red]O[/red]"


def _pomo_label(t: TodoItem) -> str:
    """'🍅fatti/stimati' se stimato, '🍅xN' se solo fatti, '' altrimenti."""
    try:
        done = int(t.pomodoros or 0)
    except (ValueError, TypeError):
        done = 0
    try:
        stima = int(getattr(t, "stima_pomo", 0) or 0)
    except (ValueError, TypeError):
        stima = 0
    if stima > 0:
        return f"🍅{done}/{stima}"
    if done > 0:
        return f"🍅x{done}"
    return ""


HEALTH_CRIT_LATE = 3


HEALTH_CRIT_RATIO = 0.25
