"""Modello temporale esplicito del Planner (F0, puro, niente I/O/UI/i18n).

Primitive condivise da scheduler, replan e adapter UI:

- ``fuse()``: fonde availability sovrapposte/contenute/contigue/duplicati.
- ``clip_future()``: rende gli slot passati indisponibili (``start =
  max(start, now)``). Niente buffer operativo in questa iterazione.
- ``residual()``: minuti effettivamente liberi nel futuro (availability
  meno busy dopo ``now``) — il "tempo residuo", distinto dalla capacita'
  residua in pomodori (``capacity - planned``).
- ``slack()``: definizione canonica unica di slack in tutto il planner:
  ``slack = deadline - now - duration`` (minuti, puo' essere negativo).
  Stessa definizione in F2/F3/evidence/test/narrative.

Policy: wall-time naive ovunque (convenzione repo); tollerante in ingresso
(garbage -> scartato, mai eccezioni); deterministico a parita' di input.
"""

from datetime import date, datetime

from carpediem.planner.models import TimeWindow

_REAL_DATE = date
_REAL_DATETIME = datetime


def _valid_windows(windows) -> list:
    """TimeWindow valide (datetime, start < end), scarti silenziosi."""
    out = []
    try:
        items = list(windows or ())
    except TypeError:
        return []
    for w in items:
        if not isinstance(w, TimeWindow):
            continue
        try:
            start, end = w.start, w.end
        except AttributeError:
            continue
        if not isinstance(start, _REAL_DATETIME) or not isinstance(end, _REAL_DATETIME):
            continue
        if start < end:
            out.append(TimeWindow(start, end))
    return out


def _as_moment(now):
    """now -> datetime, o None se non interpretabile."""
    if now is None:
        return None
    if isinstance(now, _REAL_DATETIME):
        return now
    if isinstance(now, _REAL_DATE):
        return datetime(now.year, now.month, now.day)
    return None


def as_moment(now):
    """Forma pubblica di _as_moment: qualunque date/datetime -> datetime.

    Usa le classi stdlib reali (mai nomi patchabili dai test): gli adapter
    UI la usano per normalizzare `now` in modo freeze-proof.
    """
    return _as_moment(now)


def fuse(windows) -> list:
    """Fonde finestre sovrapposte/contenute/contigue/duplicati (puro).

    Ordina per (start, end) e fonde quando ``next.start <= cur.end``:
    copre sovrapposizioni, contenimento totale, adiacenza esatta e
    duplicati. Finestre invalide scartate. Finestre di giorni diversi
    restano separate salvo sovrapposizione assoluta (aritmetica sui
    datetime, mai per-data). Deterministico.
    """
    valid = _valid_windows(windows)
    valid.sort(key=lambda w: (w.start, w.end))
    merged: list = []
    for w in valid:
        if merged and w.start <= merged[-1].end:
            cur = merged[-1]
            merged[-1] = TimeWindow(cur.start, max(cur.end, w.end))
        else:
            merged.append(w)
    return merged


def clip_future(availability, now) -> list:
    """Availability con gli slot passati indisponibili (puro).

    ``start = max(start, now)``; ``now`` None = nessuna clip (restituisce
    le valide cosi' come sono); ``now`` date = mezzanotte. Solo il futuro
    del giorno di ``now``: finestre con ``start`` di altro giorno scartate,
    salvo spanning overnight che copre ``now`` (``start <= now < end``).
    """
    valid = _valid_windows(availability)
    moment = _as_moment(now)
    if moment is None:
        return valid
    try:
        today = moment.date()
    except Exception:
        return valid
    out = []
    for w in valid:
        try:
            same_day = w.start.date() == today
            spans_now = w.start <= moment < w.end
        except Exception:
            continue
        if not (same_day or spans_now):
            continue
        start = max(w.start, moment)
        if start < w.end:
            out.append(TimeWindow(start, w.end))
    return out


def residual(availability, busy, now) -> int:
    """Minuti liberi nel futuro: (fused avail clip-now) meno busy (puro).

    Il "tempo residuo" (minuti di orologio), distinto dalla "capacita'
    residua" (pomodori). Busy fuso come availability; sottrazione per
    intervalli; somma arrotondata al minuto intero per difetto.
    """
    moment = _as_moment(now)
    fused_avail = fuse(availability)
    fused_busy = fuse(busy)
    future = clip_future(fused_avail, moment) if moment is not None else fused_avail
    if not future:
        return 0
    total = 0
    for f in future:
        cur = f.start
        for b in fused_busy:
            if b.end <= cur or b.start >= f.end:
                continue
            if b.start > cur:
                total += int((min(b.start, f.end) - cur).total_seconds() // 60)
            if b.end > cur:
                cur = b.end
            if cur >= f.end:
                break
        if cur < f.end:
            total += int((f.end - cur).total_seconds() // 60)
    return max(0, total)


def slack(deadline, now, duration_min) -> int | None:
    """Slack canonico (minuti): ``(deadline - now) - duration`` (puro).

    Unica definizione valida in F2/F3/evidence/narrative/test. None se
    deadline/now/duration non interpretabili. Puo' essere negativo (slot
    gia' impossibile o deadline stretta).
    """
    if not isinstance(deadline, _REAL_DATETIME):
        return None
    moment = _as_moment(now)
    if moment is None:
        return None
    try:
        duration = int(duration_min or 0)
    except (ValueError, TypeError):
        return None
    if duration < 0:
        return None
    try:
        delta_min = int((deadline - moment).total_seconds() // 60)
    except Exception:
        return None
    return delta_min - duration


def deadline_at(deadlines, todo_id, day) -> datetime | None:
    """Limite di fine-slot da mappa scadenze, o None se non applicabile.

    Solo due-date == day + orario HH:MM valido con range reali (stessa
    semantica di scheduler._deadline, che delega qui dal F3): scaduti,
    futuri, senza-ora, garbage e mappa assente -> None. Totale, mai solleva.
    """
    try:
        due_s, due_t = (deadlines or {}).get(todo_id, ("", ""))
    except (AttributeError, TypeError, ValueError):
        return None
    try:
        day_iso = day.isoformat()
    except AttributeError:
        return None
    if not due_t or str(due_s or "")[:10] != day_iso:
        return None
    try:
        text = str(due_t)
        h, m = int(text[:2]), int(text[3:5])
        if not (0 <= h <= 23 and 0 <= m <= 59 and text[2:3] == ":"):
            return None
    except (ValueError, TypeError, IndexError):
        return None
    try:
        return datetime(day.year, day.month, day.day, h, m)
    except (ValueError, AttributeError):
        return None
