"""Persistenza: paths, load/save todos/template/config/archive/pomodoro/backup."""

import json
import re
from datetime import datetime
from pathlib import Path

from src import crypto as _crypto
from src.lang import T
from src.models import Priority, TodoItem


def _read_state_file(path: Path):
    """Legge JSON con envelope cifrato opzionale.

    Solleva ValueError se il file e' cifrato e la password manca/errata,
    o se il contenuto non e' JSON valido.
    """
    text = path.read_text(encoding="utf-8")  # OSError se manca
    obj, _ = _crypto.unprotect_text(text)
    return obj


def _dump_state_text(obj) -> str:
    """Serializza JSON applicando la cifratura se il lock e' attivo."""
    return _crypto.protect_text(json.dumps(obj, indent=2, ensure_ascii=False))


def state_readable() -> bool:
    """True se il file todos esiste ed e' leggibile (chiave corretta se cifrato)."""
    if not DATA_FILE.exists():
        return True
    try:
        _read_state_file(DATA_FILE)
    except (OSError, ValueError):
        return False
    return True


class StorageLocked(OSError):
    """Altro processo detiene il lock oltre il timeout."""


LOCK_TIMEOUT = 10.0


def _locked(path: Path, timeout: float = LOCK_TIMEOUT):
    """Lock esclusivo inter-processo con timeout (fcntl su Unix, msvcrt su Windows).

    Protocollo: un sidecar `<nome>.lock` per ogni file di stato; ogni
    scrittura/lettura protetta acquisisce il lock del file che tocca, in
    sequenza e mai annidati (niente inversioni d'ordine). La mutua
    esclusione vale tra processi dello STESSO sistema operativo (su Unix
    flock whole-file, su Windows region-lock di 1 byte sullo stesso
    sidecar: meccanismi diversi, stessa granularita' per file).
    Il kernel/OS rilascia il lock alla morte del processo: niente lock stali.
    Solleva StorageLocked se scade il timeout.
    """
    import contextlib
    import os
    import time

    try:
        import fcntl  # type: ignore[import-not-found]
    except ImportError:
        fcntl = None  # type: ignore[assignment]
    try:
        import msvcrt  # type: ignore[import-not-found]
    except ImportError:
        msvcrt = None  # type: ignore[assignment]

    @contextlib.contextmanager
    def _acquire():
        if fcntl is None and msvcrt is None:
            raise OSError("lock inter-processo non supportato su questa piattaforma")
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = path.parent / (path.name + ".lock")
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_BINARY", 0)
        fd = os.open(lock_path, flags, 0o644)
        try:
            if msvcrt is not None and fcntl is None:
                os.lseek(fd, 0, os.SEEK_SET)

            def _try_lock() -> None:
                if fcntl is not None:
                    # Ramo Unix-only (su Windows fcntl non esiste e non si arriva qui).
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined]
                else:
                    assert msvcrt is not None
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)

            def _unlock() -> None:
                try:
                    if fcntl is not None:
                        fcntl.flock(fd, fcntl.LOCK_UN)  # type: ignore[attr-defined]
                    elif msvcrt is not None:
                        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass

            # fcntl segnala la contesa con BlockingIOError, msvcrt con OSError.
            _busy = (BlockingIOError,) if fcntl is not None else (OSError,)
            deadline = time.monotonic() + timeout
            while True:
                try:
                    _try_lock()
                    break
                except _busy:
                    if time.monotonic() >= deadline:
                        raise StorageLocked(f"File occupato oltre timeout: {path.name}")
                    time.sleep(0.05)
            yield
        finally:
            _unlock()
            os.close(fd)

    return _acquire()


def _write_locked(path: Path, text: str, with_bak: bool = False) -> None:
    """Scrittura atomica tmp+fsync+replace. Il chiamante detiene il lock."""
    import os
    import shutil

    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    if with_bak and path.exists():
        try:
            shutil.copy2(path, path.with_suffix(".bak.json"))
        except OSError:
            pass
    tmp.replace(path)


def _write_atomic(path: Path, text: str, with_bak: bool = False) -> None:
    """Scrittura atomica sotto lock esclusivo."""
    with _locked(path):
        _write_locked(path, text, with_bak=with_bak)


def _is_locked_no_key(path: Path) -> bool:
    """True se il file e' un envelope cifrato e non abbiamo la chiave in RAM."""
    if _crypto.is_unlocked():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    try:
        return _crypto.is_envelope(text)
    except Exception:
        return False


def _is_crypto_unreadable(path: Path) -> bool:
    """True se il file esiste, e' un envelope ma non e' decifrabile con la
    chiave corrente (errata o assente). Il contenuto non e' interpretabile:
    il merge non deve trattarlo come 'tutto cancellato' (es. cambio password
    in corso), ma come disco non leggibile."""
    if not path.exists():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    try:
        if not _crypto.is_envelope(text):
            return False
    except Exception:
        return False
    try:
        _crypto.unprotect_text(text)
    except Exception:
        return True
    return False


def _read_dict_list(path: Path) -> list[dict]:
    """Dict grezzi dal file. Mancante -> []. Corrotto -> backup .corrotto + [].
    Bloccato (cifrato senza chiave) -> [] SENZA backup: non e' corrotto."""
    if not path.exists():
        return []
    try:
        data = _read_state_file(path)
    except (json.JSONDecodeError, OSError, ValueError):
        if _is_locked_no_key(path):
            return []
        backup = path.with_suffix(".corrotto.json")
        try:
            backup.write_bytes(path.read_bytes())
        except OSError:
            pass
        return []
    if not isinstance(data, list):
        return []
    return [d for d in data if isinstance(d, dict)]


def _home() -> Path:
    """Base dati: TASKO_HOME se impostata (test/automazioni), altrimenti home reale."""
    import os

    override = os.environ.get("TASKO_HOME", "").strip()
    if override:
        base = Path(override).expanduser()
        base.mkdir(parents=True, exist_ok=True)
        return base
    return Path.home()


DATA_FILE = _home() / ".todo_app.json"


def load_todos() -> list[TodoItem]:
    todos: list[TodoItem] = []
    for item in _read_dict_list(DATA_FILE):
        try:
            todos.append(TodoItem.from_dict(item))
        except Exception:
            continue
    return todos


def _save_todos_plain(todos: list[TodoItem]) -> None:
    """Scrittura semplice sotto lock (nessun merge, nessuna base).

    Solo per seed/test: aggira merge e _base. Il codice di produzione
    scrive i todos ESCLUSIVAMENTE via TodoStore.commit() (guardrail:
    test_plain_mai_in_produzione). Gli store vivi restano coerenti: il
    prossimo commit() rilegge il disco e fonde (merge three-way)."""
    _write_atomic(
        DATA_FILE,
        _dump_state_text([t.to_dict() for t in todos]),
        with_bak=True,
    )


def _dicts_by_id(dicts: list[dict]) -> tuple[dict[int, dict], list[dict]]:
    by_id: dict[int, dict] = {}
    noids: list[dict] = []
    for d in dicts:
        if isinstance(d, dict) and isinstance(d.get("id"), int):
            by_id[d["id"]] = d
        elif isinstance(d, dict):
            noids.append(d)
    return by_id, noids


def _noid_key(d: dict) -> dict:
    """Forma canonica di un item senza id (a meno di normalizzazione from/to_dict):
    i dict grezzi su disco e quelli espansi in memoria diventano confrontabili."""
    try:
        canon = TodoItem.from_dict(d).to_dict()
        canon.pop("id", None)
        return canon
    except Exception:
        return d


def merge_todo_dicts(
    base: list[dict], disk: list[dict], ours: list[dict]
) -> list[dict]:
    """Merge three-way per id: base=ultimo stato sincronizzato,
    disk=contenuto attuale su disco, ours=memoria.

    - nuovi da entrambi i lati: unione;
    - stesso id modificato da un solo lato: vince quel lato;
    - modificato da entrambi: vinciamo noi (chi salva);
    - cancellato da un lato con l'altro intonso: resta cancellato;
    - cancellato da un lato ma modificato dall'altro: vince la modifica;
    - stesso id creato da entrambi con contenuti diversi: disco tiene l'id,
      il nostro viene riassegnato.
    - item senza id: i nostri restano, dal disco solo i davvero nuovi
      (non gia' visti e non in base).
    """
    base_by, base_no = _dicts_by_id(base)
    disk_by, disk_no = _dicts_by_id(disk)
    ours_by, ours_no = _dicts_by_id(ours)
    ids = list(ours_by) + [i for i in disk_by if i not in ours_by]
    fresh = max(list(ours_by) + list(disk_by) + list(base_by), default=0) + 1
    merged: dict[int, dict] = {}
    remap: dict[int, int] = {}  # id collisi (padre nostro) -> nuovo id riassegnato
    ours_origin: set[int] = set()  # chiavi merged arrivate dal nostro lato
    for i in ids:
        b = base_by.get(i)
        k = disk_by.get(i)
        o = ours_by.get(i)
        if o is not None and k is None:
            if b is None or o != b:
                merged[i] = (
                    o  # nuovo nostro, o modificato da noi dopo la loro cancellazione
                )
                ours_origin.add(i)
            # else: cancellato da loro con noi intonsi -> resta cancellato
        elif o is None and k is not None:
            if b is None:
                merged[i] = k  # nuovo loro
            elif k != b:
                merged[i] = k  # cancellato da noi ma modificato da loro
            # else: cancellato da noi, loro intonsi -> resta cancellato
        elif o is not None and k is not None:
            if b is None:
                if o == k:
                    merged[i] = o
                    ours_origin.add(i)
                else:
                    merged[i] = k  # collisione: disco tiene l'id...
                    d = dict(o)
                    d["id"] = fresh  # ...noi riassegnati
                    remap[i] = fresh
                    fresh += 1
                    merged[d["id"]] = d
                    ours_origin.add(d["id"])
            elif o == b:
                merged[i] = k
            elif k == b:
                merged[i] = o
                ours_origin.add(i)
            else:
                merged[i] = o  # entrambi modificato: vince chi salva
                ours_origin.add(i)
        # else: cancellato da entrambi -> niente
    # I figli creati dal nostro lato con parent_id sull'id colliso seguono
    # il padre riassegnato, non quello del disco che ha tenuto l'id.
    # (copia prima di ritoccare: i dict d'ingresso non si mutano mai)
    for mid in ours_origin:
        entry = merged.get(mid)
        if isinstance(entry, dict) and entry.get("parent_id") in remap:
            entry = dict(entry)
            while entry.get("parent_id") in remap:
                entry["parent_id"] = remap[entry["parent_id"]]
            merged[mid] = entry
    out = list(merged.values())
    out.extend(ours_no)
    ours_canon = [_noid_key(d) for d in ours_no]
    base_canon = [_noid_key(d) for d in base_no]
    out.extend(
        d
        for d in disk_no
        if _noid_key(d) not in ours_canon and _noid_key(d) not in base_canon
    )
    return out


def save_todos_synced(current: list[dict], base: list[dict]) -> list[dict]:
    """Merge three-way sotto lock unico (lettura+merge+scrittura atomici).

    Ritorna i dict effettivamente scritti (merged). Se il disco e' cifrato
    ma non decifrabile con la chiave corrente (es. cambio password in
    corso), la memoria e' l'unica fonte di verita': si riscrive com'e',
    senza merge (l'eventuale file precedente resta in `.bak.json`)."""
    with _locked(DATA_FILE):
        if _is_crypto_unreadable(DATA_FILE):
            merged = current
        else:
            disk = _read_dict_list(DATA_FILE)
            merged = merge_todo_dicts(base, disk, current)
        _write_locked(DATA_FILE, _dump_state_text(merged), with_bak=True)
        return merged


TEMPLATE_FILE = _home() / ".todo_templates.json"

DEFAULT_TEMPLATES: dict[str, list[dict]] = {
    T("tpldef_client"): [
        {"title": T("tpldef_kickoff"), "priority": Priority.HIGH},
        {"title": T("tpldef_req"), "priority": Priority.MEDIUM},
        {"title": T("tpldef_quote"), "priority": Priority.HIGH},
        {"title": T("tpldef_contract"), "priority": Priority.MEDIUM},
        {"title": T("tpldef_setup"), "priority": Priority.LOW},
    ],
    T("tpldef_trip"): [
        {"title": T("tpldef_flights"), "priority": Priority.HIGH},
        {"title": T("tpldef_hotel"), "priority": Priority.HIGH},
        {"title": T("tpldef_checkin"), "priority": Priority.MEDIUM},
        {"title": T("tpldef_luggage"), "priority": Priority.LOW},
        {"title": T("tpldef_docs"), "priority": Priority.MEDIUM},
    ],
    T("tpldef_site"): [
        {"title": T("tpldef_wireframe"), "priority": Priority.MEDIUM},
        {"title": T("tpldef_design"), "priority": Priority.MEDIUM},
        {"title": T("tpldef_dev"), "priority": Priority.HIGH},
        {"title": T("tpldef_test"), "priority": Priority.HIGH},
        {"title": T("tpldef_deploy"), "priority": Priority.HIGH},
    ],
}


def _default_templates() -> dict[str, list[dict]]:
    """I template di default, copiati (valori, senza riferimenti a DEFAULT)."""
    return {
        k: [{"title": i["title"], "priority": i["priority"]} for i in v]
        for k, v in DEFAULT_TEMPLATES.items()
    }


def _coerce_template_item(raw: dict) -> dict | None:
    title = str(raw.get("title", "") or "").strip()
    if not title:
        return None
    try:
        priority = Priority(str(raw.get("priority", "media")))
    except ValueError:
        # Accetta anche "Priority.HIGH" o "alta" maiuscola
        try:
            priority = Priority(
                str(raw.get("priority", "media")).split(".")[-1].lower()
            )
        except ValueError:
            priority = Priority.MEDIUM
    return {"title": title, "priority": priority}


def load_templates() -> dict[str, list[dict]]:
    if not TEMPLATE_FILE.exists():
        return _default_templates()
    try:
        data = _read_state_file(TEMPLATE_FILE)
    except (json.JSONDecodeError, OSError, ValueError):
        return _default_templates()
    if not isinstance(data, dict):
        return _default_templates()
    out: dict[str, list[dict]] = {}
    for name, items in data.items():
        if not isinstance(name, str) or not name.strip() or not isinstance(items, list):
            continue
        clean = []
        for raw in items:
            if not isinstance(raw, dict):
                continue
            item = _coerce_template_item(raw)
            if item:
                clean.append(item)
        if clean:
            out[name.strip()] = clean
    return out or _default_templates()


def save_templates(templates: dict[str, list[dict]]) -> None:
    serializable = {
        name: [
            {
                "title": i["title"],
                "priority": i["priority"].value
                if isinstance(i["priority"], Priority)
                else str(i["priority"]),
            }
            for i in items
        ]
        for name, items in templates.items()
    }
    _write_atomic(TEMPLATE_FILE, _dump_state_text(serializable))


CONFIG_FILE = _home() / ".todo_config.json"
DEFAULT_CONFIG: dict = {
    "theme": "matrix",
    "kanban_visible": True,
    "kanban_mode": "grafico",
    "filter_state": "attivo",
    "daily_goal": 5,
    "weekly_goal": 25,
    "pomo_daily_goal": 8,
    "lang": "auto",
    "onboarded": False,
    "reminder_min": 10,
    "sounds": True,
    "day_hours": 6,
    "smart_lists": [],
    "day_window": None,
    "outlook": None,
}


FILTER_STATES = ("attivo", "in_sospeso", "completati", None)
SMART_STATES = ("attivo", "in_sospeso", "completati", None)
MAX_SMART_LISTS = 10
MAX_DAY_EVENTS = 30
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _valid_hhmm(value) -> str | None:
    """HH:MM canonico a 2 cifre, o None se invalido. Mai solleva."""
    if not isinstance(value, str):
        return None
    m = _TIME_RE.match(value.strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return None
    return f"{h:02d}:{mi:02d}"


def _validate_day_window(value) -> dict | None:
    """Finestra operativa del giorno scritta da Buongiorno alla conferma.

    Forma strutturata: {date, start, end, events: [{start, end, title}]} —
    gli eventi NON sono stringhe da riparsare: gia' campi separati, la
    conversione a FixedEvent nel piano giorno e' esplicita e senza parsing.
    Tollerante: qualunque problema scarta (None o evento singolo scartato),
    mai solleva. Eventi: max MAX_DAY_EVENTS, titolo <= 120 char, start < end.
    """
    if not isinstance(value, dict):
        return None
    date_s = value.get("date")
    if not isinstance(date_s, str) or not _DATE_RE.match(date_s.strip()):
        return None
    try:
        datetime.strptime(date_s.strip(), "%Y-%m-%d")
    except ValueError:
        return None
    start = _valid_hhmm(value.get("start"))
    end = _valid_hhmm(value.get("end"))
    if not start or not end or start >= end:
        return None
    raw_events = value.get("events")
    if not isinstance(raw_events, list):
        raw_events = []
    events: list[dict] = []
    for ev in raw_events:
        if not isinstance(ev, dict):
            continue
        es = _valid_hhmm(ev.get("start"))
        ee = _valid_hhmm(ev.get("end"))
        if not es or not ee or es >= ee:
            continue
        title = str(ev.get("title", "") or "").strip()
        events.append({"start": es, "end": ee, "title": title[:120]})
        if len(events) >= MAX_DAY_EVENTS:
            break
    # Titoli tutto-il-giorno (riga informativa, mai busy): stessa tolleranza.
    raw_allday = value.get("allday")
    allday: list[str] = []
    if isinstance(raw_allday, list):
        for name in raw_allday:
            clean = str(name or "").strip()
            if clean:
                allday.append(clean[:120])
                if len(allday) >= MAX_DAY_EVENTS:
                    break
    return {
        "date": date_s.strip(),
        "start": start,
        "end": end,
        "events": events,
        "allday": allday,
    }


def _validate_outlook(value) -> dict | None:
    """Configurazione Outlook (registrazione Entra propria dell'utente).

    Forma: {client_id, tenant, account, tz} — solo non-segreti (mai token:
    quelli stanno nel file dedicato 0600, mai nei backup). Tollerante come
    le altre validazioni: qualunque problema -> None, mai solleva.
    - client_id/tenant obbligatori (tenant pinato: `common`/`consumers`/
      `organizations` rifiutati, niente login multi-tenant);
    - account facoltativo (se vuoto, al primo login si adotta quello
      autenticato; dopo, il binding e' enforced dall'adapter);
    - tz zona mailbox (invalida -> default Europe/Rome).
    """
    if not isinstance(value, dict):
        return None
    client_id = str(value.get("client_id", "") or "").strip()
    tenant = str(value.get("tenant", "") or "").strip()
    if not client_id or len(client_id) > 128:
        return None
    if (
        not tenant
        or len(tenant) > 128
        or tenant.lower() in ("common", "consumers", "organizations")
    ):
        return None
    account = str(value.get("account", "") or "").strip()[:254]
    if account and "@" not in account:
        return None
    tz = str(value.get("tz", "") or "").strip() or "Europe/Rome"
    try:
        from zoneinfo import ZoneInfo

        ZoneInfo(tz)
    except Exception:
        tz = "Europe/Rome"
    return {"client_id": client_id, "tenant": tenant, "account": account, "tz": tz}


def _validate_smart_lists(value) -> list[dict]:
    """Normalizza smart_lists: AND di {state, tag, project, search}, max 10.

    Entry senza nome o con tipi errati scartate; campi vuoti = wildcard;
    tag/project/search in forma canonica strip+lower; state fuori
    SMART_STATES -> None (wildcard). Mai solleva."""
    if not isinstance(value, list):
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for entry in value:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "") or "").strip()
        if not name or name.lower() in seen:
            continue
        state = entry.get("state")
        if state not in SMART_STATES:
            state = None
        tag = entry.get("tag")
        tag = str(tag or "").strip().lower() or None
        project = entry.get("project")
        project = str(project or "").strip().lower() or None
        search = entry.get("search")
        search = str(search or "").strip().lower() or None
        seen.add(name.lower())
        out.append(
            {
                "name": name,
                "state": state,
                "tag": tag,
                "project": project,
                "search": search,
            }
        )
        if len(out) >= MAX_SMART_LISTS:
            break
    return out


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if not CONFIG_FILE.exists():
        return cfg
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return cfg
    if not isinstance(data, dict):
        return cfg
    if isinstance(data.get("theme"), str) and data["theme"].strip():
        cfg["theme"] = data["theme"].strip()
    if isinstance(data.get("kanban_visible"), bool):
        cfg["kanban_visible"] = data["kanban_visible"]
    mode = data.get("kanban_mode")
    if mode in ("grafico", "testo", "nascosto"):
        cfg["kanban_mode"] = mode
    elif isinstance(data.get("kanban_visible"), bool):
        # Retrocompat: vecchie config con solo il bool.
        cfg["kanban_mode"] = "grafico" if data["kanban_visible"] else "nascosto"
    if "filter_state" in data and data["filter_state"] in FILTER_STATES:
        cfg["filter_state"] = data["filter_state"]
    cfg["daily_goal"] = _clamp_int(data.get("daily_goal", 5), 5, 0, 100)
    cfg["weekly_goal"] = _clamp_int(data.get("weekly_goal", 25), 25, 0, 500)
    cfg["pomo_daily_goal"] = _clamp_int(data.get("pomo_daily_goal", 8), 8, 0, 100)
    lang = str(data.get("lang", "auto")).lower()
    cfg["lang"] = lang if lang in ("auto", "it", "en") else "auto"
    cfg["onboarded"] = bool(data.get("onboarded", False))
    cfg["reminder_min"] = _clamp_int(data.get("reminder_min", 10), 10, 0, 120)
    cfg["sounds"] = bool(data.get("sounds", True))
    cfg["day_hours"] = _clamp_int(data.get("day_hours", 6), 6, 1, 16)
    cfg["smart_lists"] = _validate_smart_lists(data.get("smart_lists", []))
    cfg["day_window"] = _validate_day_window(data.get("day_window"))
    cfg["outlook"] = _validate_outlook(data.get("outlook"))
    return cfg


def save_config(cfg: dict) -> None:
    payload = {
        "theme": str(cfg.get("theme", DEFAULT_CONFIG["theme"])),
        "kanban_visible": bool(cfg.get("kanban_visible", True)),
        "kanban_mode": cfg.get("kanban_mode")
        if cfg.get("kanban_mode") in ("grafico", "testo", "nascosto")
        else "grafico",
        "filter_state": cfg.get("filter_state")
        if cfg.get("filter_state") in FILTER_STATES
        else None,
        "daily_goal": _clamp_int(cfg.get("daily_goal", 5), 5, 0, 100),
        "weekly_goal": _clamp_int(cfg.get("weekly_goal", 25), 25, 0, 500),
        "pomo_daily_goal": _clamp_int(cfg.get("pomo_daily_goal", 8), 8, 0, 100),
        "onboarded": bool(cfg.get("onboarded", False)),
        "reminder_min": _clamp_int(cfg.get("reminder_min", 10), 10, 0, 120),
        "sounds": bool(cfg.get("sounds", True)),
        "day_hours": _clamp_int(cfg.get("day_hours", 6), 6, 1, 16),
        "smart_lists": _validate_smart_lists(cfg.get("smart_lists", [])),
        "day_window": _validate_day_window(cfg.get("day_window")),
        "outlook": _validate_outlook(cfg.get("outlook")),
        "lang": str(cfg.get("lang", "auto")).lower()
        if str(cfg.get("lang", "auto")).lower() in ("auto", "it", "en")
        else "auto",
    }
    _write_atomic(CONFIG_FILE, json.dumps(payload, indent=2, ensure_ascii=False))


OUTLOOK_TOKEN_FILE = _home() / ".todo_outlook_token.json"


def save_outlook_token(cache_str: str) -> None:
    """Cache token MSAL su file dedicato 0600, envelope cifrato se lock attivo.

    Mai nei backup zip (file escluso da `_backup_sources` per disegno +
    test guardrail), mai nei log. Scrittura atomica come gli altri file.
    """
    import os

    _write_atomic(OUTLOOK_TOKEN_FILE, _dump_state_text({"cache": cache_str}))
    try:
        os.chmod(OUTLOOK_TOKEN_FILE, 0o600)
    except OSError:
        pass


def load_outlook_token() -> str | None:
    """Cache token serializzata, o None (assente, illeggibile, lock spento).

    Envelope cifrato senza chiave -> None (fail-closed, mai plaintext
    di ripiego): con lock spento il fetch e' bloccato dal gate in app.
    """
    if not OUTLOOK_TOKEN_FILE.exists():
        return None
    try:
        obj = _read_state_file(OUTLOOK_TOKEN_FILE)
    except (json.JSONDecodeError, OSError, ValueError):
        return None
    if not isinstance(obj, dict) or not isinstance(obj.get("cache"), str):
        return None
    return obj["cache"]


def delete_outlook_token() -> None:
    """Revoca locale: cancella il file token (disconnessione)."""
    try:
        OUTLOOK_TOKEN_FILE.unlink(missing_ok=True)
    except OSError:
        pass


ARCHIVE_FILE = _home() / ".todo_archive.json"


def load_archive() -> list[dict]:
    if not ARCHIVE_FILE.exists():
        return []
    try:
        data = _read_state_file(ARCHIVE_FILE)
    except (json.JSONDecodeError, OSError, ValueError):
        return []
    return [d for d in data] if isinstance(data, list) else []


def save_archive(items: list[dict]) -> None:
    _write_atomic(ARCHIVE_FILE, _dump_state_text(items))


BACKUP_DIR = _home() / "Tasko_backups"


BACKUP_KEEP = 14


def _backup_sources() -> tuple[tuple[str, Path], ...]:
    return (
        ("todos", DATA_FILE),
        ("templates", TEMPLATE_FILE),
        ("pomodoro", POMODORO_FILE),
        ("config", CONFIG_FILE),
        ("archive", ARCHIVE_FILE),
    )


def list_snapshots() -> list[Path]:
    try:
        files = sorted(BACKUP_DIR.glob("tasko_*.zip"), reverse=True)
    except OSError:
        return []
    return [p for p in files if p.is_file()]


def _snapshot_manifest(files: dict[str, int]) -> dict:
    return {
        "app": "tasko",
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "files": files,
    }


def create_backup() -> Path:
    """Crea uno snapshot zip di tutti i file di stato + manifest. Ritorna il path."""
    import zipfile

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    # Microsecondi + contatore anti-collisione: due backup nello stesso
    # istante non devono mai sovrascriversi (ZipFile(out, "w") tronca).
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    out = BACKUP_DIR / f"tasko_{ts}.zip"
    n = 0
    while out.exists():
        n += 1
        out = BACKUP_DIR / f"tasko_{ts}_{n}.zip"
    counts: dict[str, int] = {}
    # Lettura di ogni sorgente sotto il suo lock: niente snapshot a meta'
    # di una scrittura concorrente (torn read), niente lock annidati.
    snapshots: list[tuple[str, bytes]] = []
    for name, path in _backup_sources():
        if not path.exists():
            continue
        try:
            with _locked(path):
                snapshots.append((name, path.read_bytes()))
        except OSError:
            continue  # sparito nel frattempo: snapshot senza quel file
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in snapshots:
            zf.writestr(f"{name}.json", data)
            try:
                counts[name] = (
                    len(json.loads(data)) if name in ("todos", "archive") else 1
                )
            except (json.JSONDecodeError, OSError):
                counts[name] = -1
        zf.writestr("manifest.json", json.dumps(_snapshot_manifest(counts), indent=2))
    # Verifica integrita' subito.
    with zipfile.ZipFile(out) as zf:
        bad = zf.testzip()
    if bad is not None:
        try:
            out.unlink()
        except OSError:
            pass
        raise OSError(f"Snapshot corrotto, scartato: {bad}")
    prune_snapshots()
    return out


def prune_snapshots(keep: int = BACKUP_KEEP) -> None:
    for old in list_snapshots()[keep:]:
        try:
            old.unlink()
        except OSError:
            pass


def snapshot_info(path: Path) -> dict:
    """Legge il manifest di uno snapshot (mai eccezioni)."""
    import zipfile

    info: dict = {"name": path.name, "size": 0, "created": "?", "files": {}}
    try:
        info["size"] = path.stat().st_size
        with zipfile.ZipFile(path) as zf:
            raw = zf.read("manifest.json")
        manifest = json.loads(raw)
        info["created"] = str(manifest.get("created", "?"))
        info["files"] = dict(manifest.get("files", {}))
    except Exception:
        pass
    return info


def _write_bytes_locked(path: Path, data: bytes) -> None:
    """Scrittura binaria atomica tmp+fsync+replace. Il chiamante detiene il lock."""
    import os
    import shutil

    tmp = path.with_suffix(".restore_tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    shutil.move(str(tmp), str(path))


def restore_snapshot(path: Path) -> None:
    """Sostituisce i file di stato con quelli dello snapshot (solo file presenti).

    Prima salva lo stato corrente con create_backup (rollback), valida che
    ogni entry sia JSON e poi scrive ogni file sotto il SUO lock con
    tmp+fsync+replace: un restore fallito lascia i dest intatti (vecchi
    contenuti riscritti) e non perde mai dati."""
    import zipfile

    try:
        zf = zipfile.ZipFile(path)
    except Exception as exc:
        raise OSError(f"Snapshot illeggibile: {exc}")
    with zf:
        bad = zf.testzip()
        if bad is not None:
            raise OSError(f"Snapshot danneggiato: {bad}")
        names = set(zf.namelist())
        wanted = [(n, d) for n, d in _backup_sources() if f"{n}.json" in names]
        if not wanted:
            return
        payloads = [(name, dest, zf.read(f"{name}.json")) for name, dest in wanted]
        for name, _dest, raw in payloads:
            try:
                json.loads(raw)
            except ValueError:
                raise OSError(f"Snapshot danneggiato: {name}.json non e' JSON")
        create_backup()  # rollback dello stato corrente
        olds: list[tuple[Path, bytes | None]] = []
        for _name, dest, _raw in payloads:
            with _locked(dest):
                try:
                    olds.append((dest, dest.read_bytes()))
                except OSError:
                    olds.append((dest, None))
        done: list[tuple[Path, bytes | None]] = []
        try:
            for (_name, dest, raw), (_dold, old) in zip(payloads, olds):
                with _locked(dest):
                    _write_bytes_locked(dest, raw)
                done.append((dest, old))
        except Exception:
            for dest, old in done:  # rollback dei file gia' sostituiti
                try:
                    with _locked(dest):
                        if old is None:
                            try:
                                dest.unlink()
                            except OSError:
                                pass
                        else:
                            _write_bytes_locked(dest, old)
                except OSError:
                    pass
            raise


POMODORO_FILE = _home() / ".todo_pomodoro.json"


POMO_PHASES = ("focus", "short", "long")
POMO_PHASE_PRESETS: dict[str, tuple[int, ...]] = {
    "focus": (15, 25, 50),
    "short": (3, 5, 10),
    "long": (10, 15, 30),
}

POMO_DEFAULTS: dict = {
    "default_minutes": 25,
    "short_minutes": 5,
    "long_minutes": 15,
    "long_every": 4,
    "cycle": 0,
    "session": None,
}


def _clamp_int(value, default: int, lo: int, hi: int) -> int:
    try:
        v = int(value)
    except (ValueError, TypeError):
        return default
    return v if lo <= v <= hi else default


def load_pomodoro() -> dict:
    """Ritorna config ciclo + sessione. Retrocompatibile coi file vecchi."""
    cfg = dict(POMO_DEFAULTS)
    if not POMODORO_FILE.exists():
        return cfg
    try:
        data = _read_state_file(POMODORO_FILE)
    except (json.JSONDecodeError, OSError, ValueError):
        return cfg
    if not isinstance(data, dict):
        return cfg
    cfg["default_minutes"] = _clamp_int(data.get("default_minutes", 25), 25, 1, 180)
    cfg["short_minutes"] = _clamp_int(data.get("short_minutes", 5), 5, 1, 60)
    cfg["long_minutes"] = _clamp_int(data.get("long_minutes", 15), 15, 1, 60)
    cfg["long_every"] = _clamp_int(data.get("long_every", 4), 4, 2, 12)
    cfg["cycle"] = _clamp_int(data.get("cycle", 0), 0, 0, 1000)
    session = data.get("session")
    if isinstance(session, dict):
        if session.get("phase") not in POMO_PHASES:
            session["phase"] = "focus"
        cfg["session"] = session
    return cfg


def save_pomodoro(state: dict) -> None:
    payload = {
        "default_minutes": _clamp_int(state.get("default_minutes", 25), 25, 1, 180),
        "short_minutes": _clamp_int(state.get("short_minutes", 5), 5, 1, 60),
        "long_minutes": _clamp_int(state.get("long_minutes", 15), 15, 1, 60),
        "long_every": _clamp_int(state.get("long_every", 4), 4, 2, 12),
        "cycle": _clamp_int(state.get("cycle", 0), 0, 0, 1000),
        "session": state.get("session")
        if isinstance(state.get("session"), dict)
        else None,
    }
    _write_atomic(POMODORO_FILE, _dump_state_text(payload))
