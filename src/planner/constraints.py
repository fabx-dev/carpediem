"""Vincoli di ammissibilita' alla proposta (puri, niente I/O).

Classificazione del comportamento storico:
- hard/silenziosi (esclusi dalla proposta senza motivo): stato != "attivo",
  id None. Completati e sospesi non compaiono mai.
- hard-con-override (mai tagliati dalla capacita'): mandatory da scoring
  (scaduto/oggi) e gia' pianificati oggi — consumati da capacity, non qui.
- esclusione-con-spiegazione: scartati oggi (plan_skip == today) vanno in
  fondo con motivo, mai preselezionati, fuori dal consumo di capacita';
  domani si ripropongono.
Tutto il resto (priorita', scadenze future, stale) e' merito, non vincolo:
vive in scoring.
"""

from src.planner import explain
from src.planner.scoring import rank_key


def is_eligible(todo) -> bool:
    """Solo task attivi con id (hard constraint, esclusione silenziosa)."""
    return todo.state == "attivo" and todo.id is not None


def is_skipped(todo, today_s: str) -> bool:
    """Scartato oggi: escluso dalla selezione ma mostrato in fondo."""
    return getattr(todo, "plan_skip", "") == today_s


def partition(scored: list, today_s: str) -> tuple[list, list]:
    """(candidati, scartati): gli scartati ricevono il motivo e sono ordinati
    per merito; i candidati (inclusi i mandatory) vanno a capacity."""
    candidates = []
    skipped = []
    for t, result, reasons, mandatory in scored:
        if is_skipped(t, today_s):
            skipped.append((t, result, [*reasons, explain.skipped()]))
        else:
            candidates.append((t, result, reasons, mandatory))
    skipped.sort(key=rank_key)
    return candidates, [(t, result, reasons) for t, result, reasons in skipped]
