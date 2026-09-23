"""Adapter Outlook/Microsoft 365: JSON calendarView -> FixedEvent puri (Fase B1).

Solo parsing, niente rete e niente auth (quelli vivono in B2): prende il
payload di `GET /me/calendarView` e restituisce vincoli temporali per lo
scheduler (`events_to_busy`), mai Task e mai decisioni di planning.

Convenzioni (sicurezza-max, fail-closed):
- scope congelato a `Calendars.Read` delegato (mai mail/contatti/file, mai
  permessi applicativi): la costante e' blindata da test guardrail;
- endpoint consentiti: solo `GRAPH_BASE_URL` + login sul tenant pinnato
  (`LOGIN_AUTHORITY` con tenant-id esplicito, mai `common`);
- fusi: Graph restituisce `dateTime` senza offset + nome zona Windows; la
  conversione a wall-time naive (convenzione del repo) richiede una zona
  nota — nomi ignoti = voce scartata e segnalata, mai indovinata;
- filtri: `showAs=free` e all-day esclusi (non occupano la giornata),
  overnight clippati dallo scheduler a valle (qui restano integri);
- cap: max 30 eventi, titoli strip + max 120 char (stessi limiti di
  `day_window` in storage: niente secondo algoritmo, solo coerenza).

Ritorna `(eventi, tutto_il_giorno, scartati)`: gli all-day NON sono busy
(non occupano ore) ma vengono restituiti a parte come riga informativa;
gli scartati sono titoli/motivi per l'hint (non bloccanti, come
`parse_event_lines`). Deterministico: ordina per (start, end, title).
Mai solleva su payload malformato (tollerante come `_validate_day_window`).
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.planner.models import FixedEvent

# --- costanti congelate (test guardrail: non allargare mai) -----------------
#: Unico scope OAuth: lettura calendario delegata (con 2FA dell'utente).
GRAPH_SCOPES = ("Calendars.Read",)
#: Unico endpoint dati consentito (niente http, niente altri host).
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
#: Authority con tenant pinnato (`{tenant}` = tenant-id aziendale, mai common).
LOGIN_AUTHORITY = "https://login.microsoftonline.com/{tenant}"

MAX_OUTLOOK_EVENTS = 30
MAX_OUTLOOK_TITLE = 120

#: showAs che NON occupano la giornata (case-insensitive, resto incluso).
_FREE_SHOW_AS = {"free"}

#: Mappatura minima Windows -> IANA (solo cio' che serve: ignoto = scarto).
_WINDOWS_TO_IANA = {
    "UTC": "UTC",
    "GMT Standard Time": "Europe/London",
    "W. Europe Standard Time": "Europe/Rome",
    "Central European Standard Time": "Europe/Rome",
    "Romance Standard Time": "Europe/Rome",
    "Central Europe Standard Time": "Europe/Rome",
    "E. Europe Standard Time": "Europe/Helsinki",
    "Eastern Standard Time": "America/New_York",
    "Pacific Standard Time": "America/Los_Angeles",
}


def _zone(name: str | None, fallback: ZoneInfo) -> ZoneInfo | None:
    """ZoneInfo dal nome Windows/IANA, o None se sconosciuta (fail-closed)."""
    if not name or not str(name).strip():
        return fallback
    key = str(name).strip()
    try:
        return ZoneInfo(_WINDOWS_TO_IANA.get(key, key))
    except (ZoneInfoNotFoundError, ValueError):
        return None


def _parse_dt(raw: str | None, item_tz: str | None, fallback: ZoneInfo):
    """dateTime Graph -> wall-time naive nella zona data, o None se invalido.

    Accetta sia naive (`...T09:00:00[.0000000]`, interpretati nella zona
    dell'evento) sia aware con offset (convertiti). Mai aware in uscita:
    il repo usa wall-time naive ovunque.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        dt = datetime.fromisoformat(raw.strip())
    except ValueError:
        return None
    if dt.tzinfo is None:
        zone = _zone(item_tz, fallback)
        if zone is None:
            return None
        try:
            # Wall-time nella zona dell'evento -> convertito alla mailbox.
            return dt.replace(tzinfo=zone).astimezone(fallback).replace(tzinfo=None)
        except (ValueError, OverflowError):
            return None
    try:
        return dt.astimezone(fallback).replace(tzinfo=None)
    except (ValueError, OverflowError):
        return None


def parse_graph_events(
    payload: dict | None, day_s: str, tz: str = "Europe/Rome"
) -> tuple[list[FixedEvent], list[str], list[str]]:
    """(eventi, tutto_il_giorno, scartati) dal JSON di calendarView per `day_s`.

    `tz` = zona della mailbox (B2 la allinea con header `Prefer:
    outlook.timezone`): serve per i naive e come target degli aware.
    Solo eventi che intersecano il giorno; ordinati per (start, end, title).
    Gli all-day con titolo sono riga informativa (mai busy); quelli senza
    titolo finiscono negli scartati (rumore in UI, trasparenza nel conteggio).
    """
    try:
        day = datetime.strptime(day_s, "%Y-%m-%d")
    except (ValueError, TypeError):
        return [], [], []
    try:
        fallback = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        return [], [], []
    lo, hi = day, day + timedelta(days=1)
    raw_items = payload.get("value") if isinstance(payload, dict) else None
    if not isinstance(raw_items, list):
        return [], [], []
    events: list[FixedEvent] = []
    allday: list[str] = []
    skipped: list[str] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("subject", "") or "").strip()[:MAX_OUTLOOK_TITLE]
        if item.get("isAllDay"):
            if title and len(allday) < MAX_OUTLOOK_EVENTS:
                allday.append(title)
            else:
                skipped.append(title or "(senza titolo)")
            continue
        if str(item.get("showAs", "") or "").strip().lower() in _FREE_SHOW_AS:
            skipped.append(title or "(senza titolo)")
            continue
        start_raw = item.get("start") or {}
        end_raw = item.get("end") or {}
        start = _parse_dt(
            start_raw.get("dateTime") if isinstance(start_raw, dict) else None,
            start_raw.get("timeZone") if isinstance(start_raw, dict) else None,
            fallback,
        )
        end = _parse_dt(
            end_raw.get("dateTime") if isinstance(end_raw, dict) else None,
            end_raw.get("timeZone") if isinstance(end_raw, dict) else None,
            fallback,
        )
        if start is None or end is None or end <= start:
            skipped.append(title or "(senza titolo)")
            continue
        if end <= lo or start >= hi:
            continue  # fuori dal giorno: non e' uno scarto, e' un altro giorno
        events.append(FixedEvent(title, start, end))
        if len(events) >= MAX_OUTLOOK_EVENTS:
            break
    events.sort(key=lambda e: (e.start, e.end, e.title))
    return events, allday, skipped
