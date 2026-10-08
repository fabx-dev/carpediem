"""Capacita' giornaliera aggregata (pura, niente I/O, niente timeline).

La capacita' resta un monte-ore giornaliero (ore -> pomodori da 0.5h), non una
timeline: calendari, finestre temporali ed eventi fissi appartengono alle fasi
successive. I mandatory (scaduti/oggi) e i gia' pianificati non si tagliano mai
e possono sforare; gli altri riempiono greedy per merito; gli esclusi hanno
motivo e restano visibili in fondo (non spariscono).

Calibrazione: il factor (da calibration.factor_for sui todos quando non
fornito, matematica in planner.estimation) corregge le stime consumate qui
senza riscrivere
mai la stima originale; scoring si limita ad annotare il motivo. Motivazione:
la calibrazione corregge durate -> appartiene alla capacita', non al merito.
"""

from src.planner import explain
from src.planner.estimation import (
    CAL_CLAMP_MAX,
    CAL_CLAMP_MIN,
    calibrated_estimate,
)
from src.planner.scoring import rank_key

POMO_HOURS = 0.5
DEFAULT_ESTIMATE = 1


def pomo_minutes(pomo) -> int:
    """Pomodori -> minuti wall-clock (UNICO convertitore nel planner).

    Usato da scheduler (durate slot), feedback e decisions (evidence):
    una sola formula, mai letterali 30/60 sparsi. Lock-step con
    domain.POMO_MINUTES (= 30, stessa unita' dal lato history — se
    POMO_HOURS cambia si aggiornano entrambi).
    """
    try:
        return max(0, int(POMO_HOURS * 60 * int(pomo or 0)))
    except (ValueError, TypeError):
        return 0


def total(hours: float) -> float:
    """Pomodori disponibili: ore / 0.5; ore invalide = 0."""
    try:
        return max(0.0, float(hours)) / POMO_HOURS
    except (ValueError, TypeError):
        return 0.0


def normalize_factor(factor: float | None) -> float | None:
    """Clamp [0.5, 3.0]; None o invalido resta None (= nessuna calibrazione)."""
    if factor is None:
        return None
    try:
        return max(CAL_CLAMP_MIN, min(CAL_CLAMP_MAX, float(factor)))
    except (ValueError, TypeError):
        return None


def estimate(todo, factor: float | None = None) -> int:
    """Stima pomodori: base stima_pomo o DEFAULT; con factor, calibrata.

    Unica fonte: domain.calibrated_estimate (stessa semantica, niente
    duplicazione; TaskView espone l'alias .stima_pomo per il seam D1);
    il factor corregge senza riscrivere mai la stima originale.
    """
    corrected, _used = calibrated_estimate(todo, factor)
    return corrected


def keep_always(entry, today_s: str) -> bool:
    """H4 (Phase 4): mandatory e gia' pianificati oggi non si tagliano mai.

    entry = (todo, score, reasons, mandatory). Lo sforamento e' rappresentato,
    non nascosto (planned_pomo puo' superare capacity_pomo)."""

    _t, _result, _reasons, mandatory = entry
    try:
        planned_today = _t.planned_for == today_s
    except AttributeError:
        planned_today = False
    return bool(mandatory or planned_today)


def allocate(
    candidates: list,
    *,
    today_s: str,
    capacity: float,
    calib: float | None,
    now=None,
    deadlines=None,
) -> list:
    """Seleziona i candidati: [(todo, score, reasons, mandatory)] in ordine finale.

    keep_always() entrano sempre (possono sforare); gli altri in ordine di
    merito finche' c'e' capienza, poi motivo di taglio. I tagliati restano in
    fondo (cut-last), mai nascosti. Il mandatory passa attraverso per il
    DayPlan (PlanItem lo porta come campo esplicito).
    now/deadlines (F3): secondario slack/durata a parita' di score via
    rank_key; None = ordinamento legacy byte-identico.
    """
    included: list[tuple] = []
    rest: list[tuple] = []
    used = 0
    for t, result, reasons, mandatory in candidates:
        if keep_always((t, result, reasons, mandatory), today_s):
            included.append((t, result, reasons, mandatory))
            used += estimate(t, calib)
        else:
            rest.append((t, result, reasons))
    rest.sort(key=lambda e: rank_key(e, now=now, deadlines=deadlines))
    for t, result, reasons in rest:
        if used + estimate(t, calib) <= capacity:
            included.append((t, result, reasons, False))
            used += estimate(t, calib)
        else:
            included.append((t, result, [*reasons, explain.cut()], False))
    included.sort(
        key=lambda e: (
            any(k == explain.CUT for k, _p in e[2]),
            *rank_key((e[0], e[1], e[2]), now=now, deadlines=deadlines),
        )
    )
    return included
