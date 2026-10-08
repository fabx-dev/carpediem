"""Matematica di stima e calibrazione (Phase 5, fonte unica del core).

Mediana anti-rumore, min-samples, clamp, stime calibrate, livelli confidence:
stesso algoritmo storicamente in domain (spostato 1:1, zero semantica).
`src/domain.py` re-esporta questi nomi per compat (UI/stats/test): unica
implementazione qui, mai duplicata. Puro, niente I/O/UI/storage: zero import
da src (le letture sono duck-typed su task/execution, mai isinstance).
"""

CAL_MIN_SAMPLES = 5
CAL_CLAMP_MIN = 0.5
CAL_CLAMP_MAX = 3.0

# Minuti wall-time per pomodoro, in lock-step con capacity.POMO_HOURS (0.5).
POMO_MINUTES = 30

# Soglie confidence (informativa, mai decisionale): LOW < 10,
# MEDIUM 10-29, HIGH >= 30 osservazioni.
CONFIDENCE_LEVELS = ("LOW", "MEDIUM", "HIGH")


def _median(sorted_vals: list) -> float | None:
    if not sorted_vals:
        return None
    mid = len(sorted_vals) // 2
    if len(sorted_vals) % 2:
        return float(sorted_vals[mid])
    return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2


def _calibration_ratios(todos: list) -> list[float]:
    """Rapporti actual/stima sui completati con entrambi > 0 (anti-rumore)."""
    ratios: list[float] = []
    for t in todos:
        try:
            est = int(t.stima_pomo or 0)
            act = int(t.actual_pomo or 0)
        except (ValueError, TypeError):
            continue
        # constraint-site: lettura stato per ratios calibrazione (non decisione)
        if t.state == "completato" and est > 0 and act > 0:
            ratios.append(act / est)
    return ratios


def calibration_samples(todos: list) -> int:
    """Quanti completati alimentano la calibrazione."""
    try:
        return len(_calibration_ratios(list(todos)))
    except TypeError:
        return 0


def calibration_factor(todos: list) -> float | None:
    """Fattore mediano actual/stima sui completati con entrambi > 0.

    None se campioni < CAL_MIN_SAMPLES; clamp [MIN, MAX] per non fidarsi
    mai ciecamente di pochi dati o outlier estremi."""
    ratios = _calibration_ratios(todos)
    if len(ratios) < CAL_MIN_SAMPLES:
        return None
    ratios.sort()
    mid = len(ratios) // 2
    median = ratios[mid] if len(ratios) % 2 else (ratios[mid - 1] + ratios[mid]) / 2
    return max(CAL_CLAMP_MIN, min(CAL_CLAMP_MAX, median))


def calibrated_estimate(todo, factor: float | None) -> tuple[int, bool]:
    """(stima_corretta, usata_calibrazione). Base = stima o 1 se assente.

    L'1 per stima assente e' un fallback di pianificazione (il piano ha
    bisogno di una durata), non una stima dichiarata dall'utente."""
    try:
        base = int(todo.stima_pomo or 0) or 1
    except (ValueError, TypeError):
        base = 1
    if factor is None:
        return base, False
    try:
        f = max(CAL_CLAMP_MIN, min(CAL_CLAMP_MAX, float(factor)))
    except (ValueError, TypeError):
        return base, False
    return max(1, round(base * f)), True


def execution_confidence(count) -> str:
    """LOW < 10, MEDIUM 10-29, HIGH >= 30. Informativa, mai decisionale."""
    try:
        n = int(count)
    except (ValueError, TypeError):
        n = 0
    if n >= 30:
        return "HIGH"
    if n >= 10:
        return "MEDIUM"
    return "LOW"


def predicted_minutes(estimate_minutes, factor) -> int:
    """predicted = estimate x factor; senza factor (o stima nulla) = estimate."""
    try:
        est = int(estimate_minutes or 0)
    except (ValueError, TypeError):
        est = 0
    if est <= 0:
        return 0
    if factor is None:
        return est
    try:
        f = max(CAL_CLAMP_MIN, min(CAL_CLAMP_MAX, float(factor)))
    except (ValueError, TypeError):
        return est
    return max(1, round(est * f))
