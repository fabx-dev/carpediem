"""Parser deterministico per inserimento task in linguaggio naturale (it/en).

Ritorna un dict con le stesse chiavi del result di TodoFormScreen, pronto per
il form (Sprint 2) e la CLI: title, priority, due, notes, recurrence, tags,
project, stima_pomo.

Sintassi (entrambe le lingue, parole chiave selezionate da `lang`):
    domani alle 17 / #tag / *progetto / !alta|!1 / ~4 / ogni lunedi /
    tra 3 giorni / 15/09 / 2026-09-15 09:30 / // nota (resto della riga)

Ambiguità fissate (coperte da test, non negoziabili senza aggiornarli):
- giorno settimanale nudo ("lunedi") = primo tale giorno STRETTAMENTE futuro
  (se oggi e' lunedi vale il prossimo: per oggi c'è "oggi").
- "lunedi prossimo" / "next monday" = quello dopo ancora (+7 giorni).
- "DD/MM" senza anno = quest'anno se futuro (oggi incluso), senno' l'anno prossimo.
  Il formato con slash e' SEMPRE DD/MM, anche in inglese.
- "HH:MM" senza data = oggi a quell'ora (anche se gia' passata: niente magie).
  Solo formato 24h: niente am/pm.
- campi scalari ripetuti (priorita', progetto, data, ora): vince l'ULTIMA
  occorrenza nel testo; i tag si uniscono (deduplicati, ordine conservato).
- token non riconosciuti ("!xyz", "*", "#" soli, date impossibili come 29/02/2026
  negli anni non bisestili) restano nel titolo.
- "// nota": solo se a inizio riga o dopo spazio (gli URL tipo https://... restano
  intatti); tutto cio' che segue va in notes, i token al suo interno NON si parsano.
- `lang` sconosciuto o mancante -> "it".
- title puo' risultare "": la validazione resta al form (n_title_req).
- parse_with_found() ritorna anche i campi trovati (per merge nel form, non overwrite).
"""

import re
from datetime import datetime, timedelta
from typing import Any

from carpediem.models import Priority, Recurrence, _normalize_due

# Giorni: liste di 7 tuple (lunedi=0 .. domenica=6), alias per lingua.
_WEEKDAYS: dict[str, list[tuple[str, ...]]] = {
    "it": [
        ("lunedì", "lunedi", "lun"),
        ("martedì", "martedi", "mar"),
        ("mercoledì", "mercoledi", "mer"),
        ("giovedì", "giovedi", "gio"),
        ("venerdì", "venerdi", "ven"),
        ("sabato", "sab"),
        ("domenica", "dom"),
    ],
    "en": [
        ("monday", "mon"),
        ("tuesday", "tue", "tues"),
        ("wednesday", "wed"),
        ("thursday", "thu", "thur", "thurs"),
        ("friday", "fri"),
        ("saturday", "sat"),
        ("sunday", "sun"),
    ],
}

_PRIORITIES: dict[str, dict[str, Priority]] = {
    "it": {"alta": Priority.HIGH, "media": Priority.MEDIUM, "bassa": Priority.LOW},
    "en": {"high": Priority.HIGH, "medium": Priority.MEDIUM, "low": Priority.LOW},
}
_PRIORITY_DIGITS = {"1": Priority.HIGH, "2": Priority.MEDIUM, "3": Priority.LOW}

_RECURRENCE_WORDS: dict[str, dict[str, Recurrence]] = {
    "it": {
        "ogni giorno": Recurrence.DAILY,
        "ogni settimana": Recurrence.WEEKLY,
        "ogni mese": Recurrence.MONTHLY,
        "ogni anno": Recurrence.YEARLY,
        "giornaliero": Recurrence.DAILY,
        "settimanale": Recurrence.WEEKLY,
        "mensile": Recurrence.MONTHLY,
        "annuale": Recurrence.YEARLY,
    },
    "en": {
        "every day": Recurrence.DAILY,
        "every week": Recurrence.WEEKLY,
        "every month": Recurrence.MONTHLY,
        "every year": Recurrence.YEARLY,
        "daily": Recurrence.DAILY,
        "weekly": Recurrence.WEEKLY,
        "monthly": Recurrence.MONTHLY,
        "yearly": Recurrence.YEARLY,
    },
}

_DATE_WORDS: dict[str, dict[str, int]] = {
    "it": {"oggi": 0, "domani": 1, "dopodomani": 2},
    "en": {"today": 0, "tomorrow": 1, "day after tomorrow": 2},
}

# (pattern, gruppo_data, gruppo_ora) per "ogni/next + giorno" e "giorno + prossimo".
_OGNI = {"it": "ogni", "en": "every"}


def _wd_lookup(lang: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for idx, names in enumerate(_WEEKDAYS[lang]):
        for name in names:
            out[name] = idx
    return out


def _wd_alternation(lang: str) -> str:
    names = [n for group in _WEEKDAYS[lang] for n in group]
    names.sort(key=len, reverse=True)
    return "|".join(re.escape(n) for n in names)


def _next_weekday(today, idx: int, extra_weeks: int = 0):
    delta = (idx - today.weekday()) % 7
    if delta == 0:
        delta = 7
    return today + timedelta(days=delta + 7 * extra_weeks)


def _resolve_slash(day: int, month: int, year: int | None, today):
    try:
        if year is None:
            cand = today.replace(month=month, day=day)
            if cand < today:
                cand = cand.replace(year=cand.year + 1)
            return cand
        if year < 100:
            year += 2000
        return today.replace(year=year, month=month, day=day)
    except ValueError:
        return None


def _compile(lang: str):
    wd_alt = _wd_alternation(lang)
    ogni = _OGNI[lang]
    rec_words = sorted(_RECURRENCE_WORDS[lang], key=len, reverse=True)
    rec_alt = "|".join(re.escape(w) for w in rec_words)
    date_words = sorted(_DATE_WORDS[lang], key=len, reverse=True)
    date_alt = "|".join(re.escape(w) for w in date_words)
    if lang == "it":
        next_pat = rf"\b(?P<wd>{wd_alt})\s+prossimo\b"
        rel_pat = r"\btra\s+(?P<n>\d+)\s+giorn[oi]\b"
    else:
        next_pat = rf"\bnext\s+(?P<wd>{wd_alt})\b"
        rel_pat = r"\bin\s+(?P<n>\d+)\s+days?\b"
    return {
        # (nome, regex, resolver(match, ctx) -> valore o None)
        "stima": (re.compile(r"~(?P<v>\d+)\b"), lambda m, c: max(0, int(m.group("v")))),
        "priority": (
            re.compile(r"!(?P<v>[\w-]+)", re.UNICODE),
            lambda m, c: (
                _PRIORITIES[lang].get(m.group("v").lower())
                or _PRIORITY_DIGITS.get(m.group("v"))
            ),
        ),
        "project": (
            re.compile(r"\*(?P<v>[\w-]+)", re.UNICODE),
            lambda m, c: m.group("v").lower(),
        ),
        "tag": (
            re.compile(r"#(?P<v>[\w-]+)", re.UNICODE),
            lambda m, c: m.group("v").lower(),
        ),
        "recurrence": (
            re.compile(rf"\b(?P<v>{rec_alt})\b", re.IGNORECASE),
            lambda m, c: _RECURRENCE_WORDS[lang].get(m.group("v").lower()),
        ),
        "ogni_wd": (
            re.compile(rf"\b{ogni}\s+(?P<wd>{wd_alt})\b", re.IGNORECASE),
            lambda m, c: ("rec+date", m.group("wd").lower()),
        ),
        "next_wd": (
            re.compile(next_pat, re.IGNORECASE),
            lambda m, c: (
                "date",
                _next_weekday(c["today"], c["wd"][m.group("wd").lower()], 1),
            ),
        ),
        "dateword": (
            re.compile(rf"\b(?P<v>{date_alt})\b", re.IGNORECASE),
            lambda m, c: (
                "date",
                c["today"] + timedelta(days=_DATE_WORDS[lang][m.group("v").lower()]),
            ),
        ),
        "relative": (
            re.compile(rel_pat, re.IGNORECASE),
            lambda m, c: ("date", c["today"] + timedelta(days=int(m.group("n")))),
        ),
        "iso": (
            re.compile(r"\b(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})\b"),
            lambda m, c: (
                "date",
                _resolve_slash(
                    int(m.group("d")), int(m.group("m")), int(m.group("y")), c["today"]
                ),
            ),
        ),
        "slash": (
            re.compile(r"\b(?P<d>\d{1,2})/(?P<m>\d{1,2})(?:/(?P<y>\d{2,4}))?\b"),
            lambda m, c: (
                "date",
                _resolve_slash(
                    int(m.group("d")),
                    int(m.group("m")),
                    int(m.group("y")) if m.group("y") else None,
                    c["today"],
                ),
            ),
        ),
        "weekday": (
            re.compile(rf"\b(?P<wd>{wd_alt})\b", re.IGNORECASE),
            lambda m, c: (
                "date",
                _next_weekday(c["today"], c["wd"][m.group("wd").lower()]),
            ),
        ),
        "time": (
            re.compile(
                r"\b(?:(?:alle|ore|at)\s+)?(?P<h>\d{1,2}):(?P<mi>\d{2})\b",
                re.IGNORECASE,
            ),
            lambda m, c: (
                f"{int(m.group('h')):02d}:{m.group('mi')}"
                if 0 <= int(m.group("h")) <= 23 and 0 <= int(m.group("mi")) <= 59
                else None
            ),
        ),
    }


def parse(text: str, lang: str = "it") -> dict:
    """Estrae i campi task da una frase in linguaggio naturale."""
    return parse_with_found(text, lang)[0]


def parse_with_found(text: str, lang: str = "it") -> tuple[dict, set[str]]:
    """Come parse(), piu' l'insieme dei campi trovati (nomi del result).

    "title" e' sempre presente (e' la fonte); "due" vale per data e/o ora.
    """
    lang = (lang or "it").lower()[:2]
    if lang not in ("it", "en"):
        lang = "it"
    today = datetime.now().date()
    ctx: dict[str, Any] = {"today": today, "wd": _wd_lookup(lang)}
    out = {
        "title": "",
        "priority": Priority.MEDIUM,
        "due": "",
        "notes": "",
        "recurrence": Recurrence.NONE,
        "tags": [],
        "project": "",
        "stima_pomo": 0,
    }
    found = {"title"}
    s = text or ""
    # Nota // per prima: il resto della riga non si parsa (solo se a inizio
    # riga o dopo spazio, cosi' gli URL restano intatti).
    nm = re.search(r"(?:^|\s)// ?", s)
    if nm:
        out["notes"] = s[nm.end() :].strip()
        found.add("notes")
        s = s[: nm.start()].rstrip()
    # Tutti i match sul testo originale: posizioni confrontabili, vince l'ultima.
    events: list[tuple[int, int, str, object]] = []  # (start, end, kind, value)
    for kind, (pattern, resolve) in _compile(lang).items():
        for m in pattern.finditer(s):
            value = resolve(m, ctx)
            if value is None:
                continue
            if kind == "ogni_wd":
                _, wd_name = value
                events.append((m.start(), m.end(), "recurrence", Recurrence.WEEKLY))
                events.append(
                    (
                        m.start(),
                        m.end(),
                        "date",
                        _next_weekday(today, ctx["wd"][wd_name]),
                    )
                )
            elif isinstance(value, tuple) and value and value[0] == "date":
                if value[1] is None:
                    continue
                events.append((m.start(), m.end(), "date", value[1]))
            else:
                events.append((m.start(), m.end(), kind, value))
    # Selezione span: vince lo span piu' esterno (start minore, a pari start il
    # piu' lungo). Eventi sullo stesso span (ogni_wd -> recurrence+date) si
    # applicano entrambi con una sola rimozione; sovrapposizioni parziali
    # difensive vengono scartate del tutto. Rimozione dal fondo (indici stabili).
    claimed: list[tuple[int, int]] = []
    applied: list[tuple[int, int, str, object]] = []
    for start, end, kind, value in sorted(events, key=lambda e: (e[0], -(e[1] - e[0]))):
        if (start, end) in claimed:
            applied.append((start, end, kind, value))
            continue
        if any(start < r_end and end > r_start for r_start, r_end in claimed):
            continue
        claimed.append((start, end))
        applied.append((start, end, kind, value))
    for start, end in sorted(set(claimed), reverse=True):
        s = s[:start] + " " + s[end:]
    by_kind: dict[str, list[object]] = {}
    for _s, _e, kind, value in sorted(applied, key=lambda e: e[0]):
        by_kind.setdefault(kind, []).append(value)
    tags: list[str] = []
    for t in by_kind.get("tag", []):
        if t not in tags:
            tags.append(str(t))
    out["tags"] = tags
    if by_kind.get("tag"):
        found.add("tags")
    for kind, key in (
        ("stima", "stima_pomo"),
        ("priority", "priority"),
        ("project", "project"),
        ("recurrence", "recurrence"),
    ):
        if by_kind.get(kind):
            out[key] = by_kind[kind][-1]
            found.add(key)
    time = by_kind.get("time", [])
    time_str = str(time[-1]) if time else ""
    dates = by_kind.get("date", [])
    if dates or time_str:
        found.add("due")
        day = dates[-1] if dates else today
        due = day.isoformat() if hasattr(day, "isoformat") else ""
        if due and time_str:
            due = f"{due} {time_str}"
        out["due"] = _normalize_due(due) if due else ""
    title = re.sub(r"\s+", " ", s).strip()
    title = re.sub(r"[\s,;:.]+$", "", title).strip()
    out["title"] = title
    return out, found
