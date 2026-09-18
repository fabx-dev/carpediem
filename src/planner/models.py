"""Modello esplicito del piano giornaliero (puro, niente I/O/UI/i18n).

DayPlan e' il contratto tra Planner e consumer: cosa e' pianificato, cosa e'
tagliato per capacita', cosa e' scartato, con quanta capacita' e quale factor.
ScheduledDayPlan aggiunge la collocazione temporale (Fase 4): quali voci
hanno uno slot e quali no — mai orari inventati, mai scheduling del Planner.

Unita': i pomodori (stima_pomo, capacita' ore/0.5). planned_pomo puo'
superare capacity_pomo: mandatory e gia'-pianificati non si tagliano mai
(semantica storica) — nessun invariante forzato, il modello rappresenta
la realta' dell'algoritmo. Gli hard-excluded (non attivi, id None) non
compaiono, come nella proposta storica.

Tempi: datetime naive wall-time (convenzione del repo, mai aware).
"""

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class PlanItem:
    """Una voce del piano: id + dati di pianificazione, mai il Todo intero."""

    todo_id: int
    score: int
    reasons: tuple = ()
    estimate_pomo: int = 1
    mandatory: bool = False


@dataclass(frozen=True)
class DayPlan:
    """Risultato/proposta del Planner per un giorno (immutabile, non CRUD)."""

    day: date
    planned: tuple = ()
    cut: tuple = ()
    skipped: tuple = ()
    capacity_pomo: float = 0.0
    planned_pomo: int = 0
    factor: float | None = None

    @property
    def items(self) -> tuple:
        """Tutte le voci in ordine legacy: pianificati, tagliati, scartati."""
        return (*self.planned, *self.cut, *self.skipped)

    def to_legacy(self) -> list:
        """Rappresentazione compatibile [(id, score, reasons)] come plan_day()."""
        return [(it.todo_id, it.score, list(it.reasons)) for it in self.items]


@dataclass(frozen=True)
class TimeWindow:
    """Intervallo [start, end): disponibilita' o busy (ruolo dal contesto)."""

    start: datetime
    end: datetime


@dataclass(frozen=True)
class ScheduledItem:
    """Voce del DayPlan collocata: riusa il PlanItem, aggiunge lo slot."""

    item: PlanItem
    start: datetime
    end: datetime


@dataclass(frozen=True)
class ScheduledDayPlan:
    """DayPlan + collocazione temporale (immutabile, non CRUD).

    scheduled/unscheduled coprono esattamente plan.planned: cut e skipped
    restano fuori dallo scheduling (gia' decisi dal Planner). Un mandatory
    senza slot resta unscheduled — mai overlap, mai ore inventate.
    """

    plan: DayPlan
    scheduled: tuple = ()
    unscheduled: tuple = ()
    availability: tuple = ()
    busy: tuple = ()
