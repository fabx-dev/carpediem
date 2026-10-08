"""Riferimenti a frasi del Planner (puro, niente I/O/UI/i18n, niente T()).

Contratto (mini-refactor phrase): il Planner produce PhraseRef, la UI li
renderizza con ``T(ref.key, **ref.params)``. Il Planner non conosce testo
né UI; la UI non ricostruisce il mapping dei tipi del Planner.

- ``PhraseRef`` e' solo dati: chiave catalogo + params template + origin
  diagnostica (developer-only, mai necessaria al rendering).
- ``phrase_for(kind, family, detail=None)`` e' l'UNICA fonte per i mapping
  kind -> chiave (blocked/replan/decision). Kind ignoto nelle famiglie
  blocked -> fallback generico onesto (mai KeyError, mai causa falsa);
  famiglia ignota o detail mancante per kind che lo richiede -> KeyError
  (errore programmatore, mai input utente: i caller restano difensivi).
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

# Varianti con numeri reali (F5, solo quando il detail porta le evidence
# max_gap_min/needed_min da diagnose): spiegano il buco insufficiente con
# i minuti veri, mai ricostruiti in UI.
_BLOCKED_LINE_GAP = {
    "busy": "why_blocked_busy_gap",
    "busy_named": "why_blocked_busy_named_gap",
    "window": "why_blocked_window_gap",
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

_BLOCKED_FRAG_GAP = {
    "busy": "why_frag_c_busy_gap",
    "busy_named": "why_frag_c_busy_named_gap",
    "window": "why_frag_c_window_gap",
}

# Fallback onesto (F5): kind futuri/sconosciuti non sollevano piu' KeyError
# ma rendono una riga generica che ammette il limite, mai una causa falsa.
_BLOCKED_LINE_UNKNOWN = "why_blocked_unknown"
_BLOCKED_FRAG_UNKNOWN = "why_frag_c_unknown"

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


def _gap_params(detail) -> dict | None:
    """{g, n} dai numeri reali di diagnose, o None se assenti/invalidi."""
    try:
        detail = dict(detail or {})
        gap = int(detail.get("max_gap_min"))
        need = int(detail.get("needed_min"))
    except (TypeError, ValueError, AttributeError):
        return None
    if gap < 0 or need <= 0:
        return None
    return {"g": gap, "n": need}


def phrase_for(kind: str, family: str, detail=None) -> PhraseRef:
    """(kind, family) -> PhraseRef con params gia' pronti per T().

    Varianti con dettaglio: busy/tasks usano i titoli solo se presenti
    (named), deadline solo con HH:MM, window/busy usano la variante gap
    con i minuti veri solo se presenti (max_gap_min + needed_min).
    Kind ignoto -> fallback generico onesto (mai KeyError, mai causa
    falsa); famiglia ignota o detail mancante per kind che lo richiede
    -> KeyError (errore programmatore, mai input utente: i caller restano
    difensivi come prima).
    """
    try:
        table, origin = _FAMILIES[family]
    except KeyError:
        raise KeyError(f"unknown phrase family: {family!r}") from None
    if kind not in table:
        if family == "blocked-line":
            return PhraseRef(_BLOCKED_LINE_UNKNOWN, {}, origin)
        if family == "blocked-frag":
            return PhraseRef(_BLOCKED_FRAG_UNKNOWN, {}, origin)
        raise KeyError(f"unknown kind {kind!r} for family {family!r}") from None
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
        gap = _gap_params(detail)
        if names is not None and gap is not None:
            key = (
                _BLOCKED_LINE_GAP["busy_named"]
                if family == "blocked-line"
                else _BLOCKED_FRAG_GAP["busy_named"]
            )
            params = {
                "e": names if isinstance(names, str) else ", ".join(names),
                **gap,
            }
        elif names is not None:
            key += "_named"
            params = {"e": names if isinstance(names, str) else ", ".join(names)}
        elif gap is not None:
            key = (
                _BLOCKED_LINE_GAP["busy"]
                if family == "blocked-line"
                else _BLOCKED_FRAG_GAP["busy"]
            )
            params = gap
    elif kind == "window":
        gap = _gap_params(detail)
        if gap is not None:
            key = (
                _BLOCKED_LINE_GAP["window"]
                if family == "blocked-line"
                else _BLOCKED_FRAG_GAP["window"]
            )
            params = gap
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
