"""Capacita' giornaliera aggregata (pura, niente I/O, niente timeline).

La capacita' resta un monte-ore giornaliero (ore -> pomodori da 0.5h), non una
timeline: calendari, finestre temporali ed eventi fissi appartengono alle fasi
successive. I mandatory (scaduti/oggi) e i gia' pianificati non si tagliano mai
e possono sforare; gli altri riempiono greedy per merito; gli esclusi hanno
motivo e restano visibili in fondo (non spariscono).

Calibrazione: il factor (da calibration.factor_for sui todos quando non
fornito, unica fonte domain) corregge le stime consumate qui senza riscrivere
mai la stima originale; scoring si limita ad annotare il motivo. Motivazione:
la calibrazione corregge durate -> appartiene alla capacita', non al merito.
"""

from src.domain import CAL_CLAMP_MAX, CAL_CLAMP_MIN, calibrated_estimate
from src.models import _due_date_part
from src.planner import explain
from src.planner.scoring import rank_key

POMO_HOURS = 0.5
DEFAULT_ESTIMATE = 1


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
    duplicazione); il factor corregge senza riscrivere mai la stima originale.
    """
    corrected, _used = calibrated_estimate(todo, factor)
    return corrected


def allocate(
    candidates: list, *, today_s: str, capacity: float, calib: float | None
) -> list:
    """Seleziona i candidati: [(todo, score, reasons, mandatory)] in ordine finale.

    Mandatory e gia' pianificati entrano sempre (possono sforare); gli altri
    in ordine di merito finche' c'e' capienza, poi motivo di taglio. I tagliati
    restano in fondo (cut-last), mai nascosti. Il mandatory passa attraverso
    per il DayPlan (PlanItem lo porta come campo esplicito)."""
    included: list[tuple] = []
    rest: list[tuple] = []
    used = 0
    for t, result, reasons, mandatory in candidates:
        if mandatory or t.planned_for == today_s:
            included.append((t, result, reasons, mandatory))
            used += estimate(t, calib)
        else:
            rest.append((t, result, reasons))
    rest.sort(key=rank_key)
    for t, result, reasons in rest:
        if used + estimate(t, calib) <= capacity:
            included.append((t, result, reasons, False))
            used += estimate(t, calib)
        else:
            included.append((t, result, [*reasons, explain.cut()], False))
    included.sort(
        key=lambda e: (
            any(k == explain.CUT for k, _p in e[2]),
            -e[1],
            _due_date_part(e[0].due) or "9999",
            e[0].id,
        )
    )
    return included
