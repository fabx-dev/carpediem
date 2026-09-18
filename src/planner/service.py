"""Application service Planner (Fase 1: boundary sopra plan_day).

Il Planner incapsula l'accesso alla logica di pianificazione esistente
senza alterarla: propose() delega a plan_day() con gli stessi parametri
e lo stesso formato di ritorno. La futura evoluzione (scoring, vincoli,
capacita', scheduling) avverra' dietro questa interfaccia.
"""

from src.models import TodoItem
from src.plan import plan_day


class Planner:
    """Boundary applicativo attorno a plan_day()."""

    def __init__(
        self,
        todos: list[TodoItem],
        *,
        today: str | None = None,
        hours: float = 6.0,
        factor: float | None = None,
    ) -> None:
        self.todos = todos
        self.today = today
        self.hours = hours
        self.factor = factor

    def propose(self) -> list:
        """Proposta giornaliera: [(id, score, reasons)] come plan_day()."""
        return plan_day(
            self.todos,
            today=self.today,
            hours=self.hours,
            factor=self.factor,
        )
