"""Export iCal puro (estratto da TodoApp, E1): niente I/O/UI.

`ical_event_lines` produce le righe VEVENT per un task; la scrittura del
file .ics resta nella action (unico punto di I/O). Esteso oltre
l'originale: UID fallback deterministico, DTEND da stima, fold RFC 5545,
CR hygiene (vedi Phase 3).
"""

import hashlib
from datetime import datetime, timedelta

from src.lang import prio_disp
from src.models import TodoItem


def ical_escape(value: str) -> str:
    return (
        str(value)
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def ical_fold(line: str, width: int = 75) -> list[str]:
    """Piega una riga .ics a <width> ottetti (RFC 5545 §3.1, CRLF+SP).
    Solo aggiunta di continuazioni: parser tolleranti leggono entrambi."""
    raw = line.encode("utf-8")
    if len(raw) <= width:
        return [line]
    out, first = [], True
    while raw:
        limit = width if first else width - 1
        chunk, rest = raw[:limit], raw[limit:]
        # Mai spezzare un codepoint UTF-8: arretra fino a decodifica valida.
        while chunk:
            try:
                text = chunk.decode("utf-8")
                break
            except UnicodeDecodeError:
                rest = chunk[-1:] + rest
                chunk = chunk[:-1]
        else:
            text = ""  # mai con width>=4 (rest contiene gia' tutto)
        out.append((" " if not first else "") + text)
        raw = rest
        first = False
    return out


def _fallback_uid(title: str, due: str) -> str:
    """UID best-effort per task senza id (mai in produzione: lo store
    assegna sempre un id). Deterministico cross-process (sha1, non hash()
    che e' salato per PYTHONHASHSEED), ma NON identita' canonica: un edit
    a titolo/scadenza cambia l'UID. Solo per non duplicare a ogni export."""
    digest = hashlib.sha1(f"{title}\x00{due}".encode("utf-8")).hexdigest()[:16]
    return f"carpediem-noid-{digest}@carpediem.local"


def ical_event_lines(
    todo: TodoItem, date_part: str, time_part: str, stamp: str
) -> list[str]:
    if todo.id:
        uid = f"carpediem-{todo.id}@carpediem.local"
    else:
        uid = _fallback_uid(todo.title, todo.due)
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
        # Durata dichiarata dalla stima (30m per pomodoro, 30m se assente:
        # stessa convenzione del planner; solo display, mai vincolo).
        # Senza DTEND i client mostrano durata zero (C1.5).
        try:
            minutes = max(1, int(todo.stima_pomo or 0)) * 30
        except (ValueError, TypeError):
            minutes = 30
        try:
            end = (
                datetime.strptime(start, "%Y%m%dT%H%M%S") + timedelta(minutes=minutes)
            ).strftime("%Y%m%dT%H%M%S")
        except ValueError:
            end = start
        lines.append(f"DTEND:{end}")
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
    folded: list[str] = []
    for line in lines:
        folded.extend(ical_fold(line))
    return folded
