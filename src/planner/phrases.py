"""Riferimenti a frasi del Planner (puro, niente I/O/UI/i18n, niente T()).

Contratto (mini-refactor phrase): il Planner produce PhraseRef, la UI li
renderizza con ``T(ref.key, **ref.params)``. Il Planner non conosce testo
né UI; la UI non ricostruisce il mapping dei tipi del Planner.

- ``PhraseRef`` e' solo dati: chiave catalogo + params template + origin
  diagnostica (developer-only, mai necessaria al rendering).
- ``phrase_for(kind, family, detail=None)`` e' l'UNICA fonte per i mapping
  kind -> chiave (blocked/replan/decision). Kind ignoto o detail mancante
  -> KeyError (errore programmatore, mai input utente: i caller restano
  difensivi come prima).
- I motivi ``explain.*`` restano tuple grezze per compat (usati in
  scoring/partition/capacity); la conversione e' ``tuple(ref)[:2]``.
"""

from typing import NamedTuple


class PhraseRef(NamedTuple):
    key: str
    params: dict = {}
    origin: str = ""


# Famiglie chiuse: ogni kind valido risolve in una chiave esistente it/en.
_BLOCKED_LINE = {
    "user_skip": "why_blocked_user_skip",
    "capacity": "why_blocked_capacity",
    "deadline": "why_blocked_deadline",
    "busy": "why_blocked_busy",
    "window": "why_blocked_window",
    "duration": "why_blocked_duration",
    "tasks": "why_blocked_tasks",
}

_BLOCKED_FRAG = {
    # Niente user_skip: DEFERRED usa why_alt_deferred, mai un frammento.
    "tasks": "why_frag_c_tasks",
    "capacity": "why_frag_c_capacity",
    "deadline": "why_frag_c_deadline",
    "busy": "why_frag_c_busy",
    "window": "why_frag_c_window",
    "duration": "why_frag_c_duration",
}

_REPLAN = {
    "kept": "cli_replan_kept",
    "moved": "cli_replan_moved",
    "dropped": "cli_replan_dropped",
    "added": "cli_replan_added",
}

_DECISION = {
    "scheduled": "why_scheduled",
    "not_scheduled": "why_not_scheduled",
    "deferred": "why_deferred",
    "constrained": "why_constrained",
    "proposed": "why_proposed",
    "no_decision": "why_no_decision",
}

_FAMILIES = {
    "blocked-line": (_BLOCKED_LINE, "blocker"),
    "blocked-frag": (_BLOCKED_FRAG, "blocker"),
    "replan": (_REPLAN, "replan"),
    "decision": (_DECISION, "decision"),
}


def _detail_value(detail, name: str):
    try:
        value = (detail or {}).get(name)
    except AttributeError:
        value = None
    if isinstance(value, str):
        value = value.strip()
    return value or None


def phrase_for(kind: str, family: str, detail=None) -> PhraseRef:
    """(kind, family) -> PhraseRef con params gia' pronti per T().

    Varianti con dettaglio: busy/tasks usano i titoli solo se presenti
    (named), deadline solo con HH:MM — senza, KeyError come per kind ignoto.
    """
    try:
        table, origin = _FAMILIES[family]
    except KeyError:
        raise KeyError(f"unknown phrase family: {family!r}") from None
    try:
        key = table[kind]
    except KeyError:
        raise KeyError(f"unknown kind {kind!r} for family {family!r}") from None
    if family not in ("blocked-line", "blocked-frag"):
        return PhraseRef(key, {}, origin)
    params: dict = {}
    if kind == "deadline":
        hhmm = _detail_value(detail, "deadline")
        if hhmm is None:
            raise KeyError(f"missing detail 'deadline' for {kind!r}")
        params = {"d": hhmm}
    elif kind == "busy":
        # Stringa display gia' pronta (la UI fa escape+join prima):
        # tupla grezza solo da chiamanti che garantiscono testo sicuro.
        names = _detail_value(detail, "busy_titles")
        if names is not None:
            key += "_named"
            params = {"e": names if isinstance(names, str) else ", ".join(names)}
    elif kind == "tasks":
        try:
            ids = (detail or {}).get("task_ids")
            names = (detail or {}).get("task_names")
        except AttributeError:
            ids, names = None, None
        if not ids or not names:
            raise KeyError(f"missing details 'task_ids'/'task_names' for {kind!r}")
        params = {"t": names}
    return PhraseRef(key, params, origin)
