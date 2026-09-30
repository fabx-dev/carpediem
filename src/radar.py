"""Geometria e caption del radar scadenze (estratto da app.py, E3).

Solo calcoli puri + stringhe i18n (src.lang, solo dati): niente DOM,
niente plotext, niente store. Il disegno sul PlotextPlot resta in app
(`_draw_radar`, legato al widget).
"""

from datetime import datetime

from src.lang import T
from src.models import TodoItem, _due_date_part

# Colori come tuple RGB: il tema "auto" di textual-plotext rimappa i nomi
# (es. "yellow" diventava viola).
RADAR_RED = (255, 80, 80)
RADAR_YELLOW = (255, 215, 0)
RADAR_MARKER = "hd"
# Mappatura cella -> dato calibrata sullo spike (S0, plotext 5.x): zero
# sempre a w//2; riga tick esclusa dall'hit-test. Se un upgrade di plotext
# sposta la geometria, il golden test fallisce rumorosamente.
RADAR_SPAN_SLOPE = 0.9283
RADAR_SPAN_OFF = -1.0
RADAR_ROW_Y = {0: 3.05, 1: 2.35, 2: 1.6, 3: 0.95}


def _radar_horizon(todo: TodoItem, today_str: str) -> int:
    """Giorni alla scadenza non cappati (i punti del radar l'hanno valida)."""
    try:
        due = datetime.strptime(_due_date_part(todo.due), "%Y-%m-%d").date()
        ref = datetime.strptime(today_str, "%Y-%m-%d").date()
    except ValueError:
        return 0
    return (due - ref).days


def _radar_span(width: int) -> int:
    """Larghezza canvas utile calibrata (S0): zero sempre a width // 2."""
    return max(1, round(RADAR_SPAN_SLOPE * width + RADAR_SPAN_OFF))


def _radar_day(col: int, width: int) -> float:
    """Colonna cella -> giorni alla scadenza (inversa del layout plotext)."""
    return (col - width // 2) * 28 / _radar_span(width)


def _radar_caption(data: dict) -> str:
    worst = data["worst"]
    wtxt = (
        " ".join(T("radar_worst_one", id=tid, h=h) for tid, h in worst)
        if worst
        else T("radar_noworst")
    )
    cap = T("radar_cap", late=data["late"], ok=data["open_ok"], worst=wtxt)
    if data["nodate"]:
        cap += T("radar_nodate", n=data["nodate"])
    return cap
