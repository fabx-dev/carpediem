"""Vincoli di ammissibilita' alla proposta (puri, niente I/O).

Catalogo hard Phase 4 (H1-H4; S1-S5 merito in scoring.py):
- H1/H2 hard/silenziosi (esclusi dalla proposta senza motivo): stato !=
  "attivo", id None. Completati e sospesi non compaiono mai -> EXCLUDED.
- H4 hard-con-override (mai tagliati dalla capacita'): mandatory da scoring
  (scaduto/oggi) e gia' pianificati oggi — consumati da capacity, non qui.
- H3 esclusione-con-spiegazione: scartati oggi (plan_skip == today) vanno in
  fondo con motivo (-> SKIPPED), mai preselezionati, fuori dal consumo di
  capacita'; domani si ripropongono.
Tutto il resto (priorita', scadenze future, stale) e' merito, non vincolo:
vive in scoring.
"""

from carpediem.planner import explain
from carpediem.planner.scoring import rank_key

# Verdetti di ammissibilita' (Phase 4, frozen come gli stati decisione):
# ELIGIBLE = entra in selezione; SKIPPED = scartato oggi con motivo (H3);
# EXCLUDED = fuori in silenzio, mai in nessuna sezione (H1/H2: il perche'
# resta interno per non cambiare l'output).
ELIGIBLE = "eligible"
SKIPPED = "skipped"
EXCLUDED = "excluded"


def is_eligible(todo) -> bool:
    """Solo task attivi con id (hard constraint, esclusione silenziosa)."""
    return todo.state == "attivo" and todo.id is not None  # constraint-site: H1/H2


def is_skipped(todo, today_s: str) -> bool:
    """Scartato oggi: escluso dalla selezione ma mostrato in fondo."""
    return getattr(todo, "plan_skip", "") == today_s


def eligibility_of(todo, today_s: str) -> str:
    """Verdetto a 3 vie (Phase 4): H1/H2 -> EXCLUDED, H3 -> SKIPPED,
    resto -> ELIGIBLE. Totale sui campi mancanti come gli helper storici."""
    if not is_eligible(todo):
        return EXCLUDED
    if is_skipped(todo, today_s):
        return SKIPPED
    return ELIGIBLE


def partition(
    scored: list, today_s: str, *, now=None, deadlines=None
) -> tuple[list, list]:
    """(candidati, scartati): gli scartati ricevono il motivo e sono ordinati
    per merito; i candidati (inclusi i mandatory) vanno a capacity.
    Entrambi tengono il flag mandatory per il DayPlan.
    now/deadlines (F3): secondario slack/durata negli scartati; None = legacy.
    """
    candidates = []
    skipped = []
    for t, result, reasons, mandatory in scored:
        if eligibility_of(t, today_s) == SKIPPED:
            skipped.append((t, result, [*reasons, explain.skipped()], mandatory))
        else:
            candidates.append((t, result, reasons, mandatory))
    skipped.sort(key=lambda e: rank_key(e, now=now, deadlines=deadlines))
    return candidates, skipped
