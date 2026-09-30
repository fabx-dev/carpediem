"""Export iCal puro (estratto da TodoApp, E1): niente I/O/UI.

`ical_event_lines` produce le righe VEVENT per un task; la scrittura del
file .ics resta nella action (unico punto di I/O). Comportamento identico
all'originale: stesso UID, stessi escape, stesso DTSTART/DTEND.
"""

from datetime import datetime, timedelta

from src.lang import prio_disp
from src.models import TodoItem


def ical_escape(value: str) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def ical_event_lines(
    todo: TodoItem, date_part: str, time_part: str, stamp: str
) -> list[str]:
    uid = f"carpediem-{todo.id or abs(hash((todo.title, todo.due)))}@carpediem.local"
    desc_bits = []
    if todo.project:
        desc_bits.append(f"Progetto: {todo.project}")
    if todo.tags:
        desc_bits.append("Tags: " + ", ".join(todo.tags))
    desc_bits.append(f"Priorita: {prio_disp(todo.priority.value)}")
    if todo.notes:
        desc_bits.append(todo.notes)
    lines = [
        "BEGIN:VEVENT",
        f"UID:{ical_escape(uid)}",
        f"DTSTAMP:{stamp}",
        f"SUMMARY:{ical_escape(todo.title)}",
        f"DESCRIPTION:{ical_escape(chr(10).join(desc_bits))}",
    ]
    if time_part:
        start = date_part.replace("-", "") + "T" + time_part.replace(":", "") + "00"
        lines.append(f"DTSTART:{start}")
    else:
        start = date_part.replace("-", "")
        try:
            end = (
                datetime.strptime(date_part, "%Y-%m-%d") + timedelta(days=1)
            ).strftime("%Y%m%d")
        except ValueError:
            end = start
        lines.append(f"DTSTART;VALUE=DATE:{start}")
        lines.append(f"DTEND;VALUE=DATE:{end}")
    lines.append("END:VEVENT")
    return lines
