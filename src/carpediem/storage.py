"""Persistenza: paths, load/save todos/template/config/archive/pomodoro/backup."""

import json
import re
from collections.abc import Callable as _Callable
from datetime import datetime
from pathlib import Path

from carpediem import crypto as _crypto
from carpediem.lang import T
from carpediem.models import Priority, TaskExecution, TodoItem


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
    if not todos_file().exists():
        return True
    try:
        _read_state_file(todos_file())
    except (OSError, ValueError):
        return False
    return True


class StorageLocked(OSError):
    """Altro processo detiene il lock oltre il timeout."""


class StorageUnreadable(OSError):
    """Il file esiste ma non e' leggibile/valido (cifrato senza chiave
    decifrabile, malformato o schema errato): i writer fail-closed
    sollevano questa invece di sovrascriverlo. Sottoclasse di OSError
    per compatibilita' con gli handler esistenti."""


def _disk_state(path: Path, expect: str = "list") -> str:
    """Stato del file persistito: MISSING / VALID / UNREADABLE / CORRUPT.

    expect: "list" (todos/archive/executions), "dict" (templates/pomodoro/
    config), "any" (solo leggibilita', mai shape).
    - MISSING: assente o 0-byte (mai scritto, scrivibile).
    - VALID: leggibile e con shape attesa.
    - UNREADABLE: envelope non decifrabile (chiave assente/errata).
      Mai .corrotto: non e' evidenza di corruzione.
    - CORRUPT: testo non JSON, o JSON con shape diversa dall'attesa.
    Letture restano tolleranti; solo i writer usano questo per rifiutare.
    """
    if not path.exists():
        return "MISSING"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return "CORRUPT"
    if not text.strip():
        return "MISSING"  # 0-byte: mai scritto, nessun dato da proteggere
    try:
        is_env = _crypto.is_envelope(text)
    except Exception:
        return "CORRUPT"
    if is_env:
        try:
            obj, _ = _crypto.unprotect_text(text)
        except Exception:
            return "UNREADABLE"
    else:
        try:
            obj = json.loads(text)
        except ValueError:
            return "CORRUPT"
    if expect == "list" and not isinstance(obj, list):
        return "CORRUPT"
    if expect == "dict" and not isinstance(obj, dict):
        return "CORRUPT"
    return "VALID"


def _ensure_writable(path: Path, expect: str = "list") -> None:
    """Fail-closed per i writer: solleva StorageUnreadable su disco
    esistente ma non leggibile/valido. MISSING e VALID passano."""
    state = _disk_state(path, expect)
    if state in ("UNREADABLE", "CORRUPT"):
        raise StorageUnreadable(f"File non leggibile, scrittura rifiutata: {path.name}")


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
            bak = path.with_suffix(".bak.json")
            bak1 = path.with_suffix(".bak.1.json")
            if bak.exists():
                bak.replace(bak1)
            shutil.copy2(path, bak)
        except OSError:
            pass
    tmp.replace(path)


def _write_atomic(
    path: Path,
    text: str,
    with_bak: bool = False,
    guard: str | None = None,
    force_rewrite: bool = False,
) -> None:
    """Scrittura atomica sotto lock esclusivo. Con guard ("list"/"dict"),
    rifiuta (StorageUnreadable) se il disco esistente non e' leggibile/valido,
    salvo force_rewrite (solo cambio password: memoria autorevole)."""
    with _locked(path):
        if guard is not None and not force_rewrite:
            _ensure_writable(path, guard)
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


def _backup_corrupt(path: Path) -> None:
    """Copia byte-identica in .corrotto.json (recupero manuale).

    Solo con evidenza di corruzione: mai su envelope non decifrabile
    (chiave errata/assente non e' corruzione)."""
    try:
        text = path.read_text(encoding="utf-8")
        if _crypto.is_envelope(text):
            return
        path.with_suffix(".corrotto.json").write_bytes(path.read_bytes())
    except OSError:
        pass


def _read_dict_list(path: Path) -> list[dict]:
    """Dict grezzi dal file. Mancante -> []. Corrotto (testo non JSON) ->
    backup .corrotto + []. Envelope non decifrabile -> [] SENZA backup:
    chiave errata/assente non e' evidenza di corruzione. Non-lista -> []
    (tollerante in lettura; i writer rifiutano via _ensure_writable)."""
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        text = ""
    if not text.strip():
        return []  # 0-byte: mai scritto, niente backup
    try:
        data = _read_state_file(path)
    except (json.JSONDecodeError, OSError, ValueError):
        try:
            is_env = _crypto.is_envelope(path.read_text(encoding="utf-8"))
        except Exception:
            is_env = False
        if is_env:
            return []
        _backup_corrupt(path)
        return []
    if not isinstance(data, list):
        return []
    return [d for d in data if isinstance(d, dict)]


# --- Percorsi applicativi --------------------------------------------------
#
# Punto canonico di risoluzione dei path runtime. Nuovi path standard per
# piattaforma (XDG su Linux, Application Support su macOS, AppData su
# Windows); i nomi legacy `.todo_*` / `Tasko_backups` restano SOLO come
# sorgenti di migrazione (LEGACY_MAP / migrate_legacy), mai come target.
# Override: CARPEDIEM_HOME (canonico) > TASKO_HOME (legacy) > default.
# Niente dipendenze esterne: solo sys.platform, environment e pathlib.
# Nessuna directory viene creata in lettura: le dir nascono al primo
# write (via _locked), quindi un fresh install non crea nulla da solo.

ENV_HOME_NEW = "CARPEDIEM_HOME"
ENV_HOME_LEGACY = "TASKO_HOME"
ENV_LANG_NEW = "CARPEDIEM_LANG"
ENV_LANG_LEGACY = "TASKO_LANG"

NEW_BACKUP_PREFIX = "carpediem_"
LEGACY_BACKUP_DIRNAME = "Tasko_backups"
LEGACY_BACKUP_PREFIX = "tasko_"


def _env_first(*names: str) -> str:
    """Primo valore non-vuoto (strip) tra le variabili date, o ""."""
    import os

    for name in names:
        val = os.environ.get(name, "").strip()
        if val:
            return val
    return ""


def home_override() -> Path | None:
    """Override esplicito della base dati, o None (default di piattaforma).

    Precedenza: CARPEDIEM_HOME > TASKO_HOME. Nessun mkdir, nessuna scrittura.
    """
    val = _env_first(ENV_HOME_NEW, ENV_HOME_LEGACY)
    return Path(val).expanduser() if val else None


def _home() -> Path:
    """Base dati legacy-compatibile: override se impostato, altrimenti home reale."""
    override = home_override()
    if override is not None:
        override.mkdir(parents=True, exist_ok=True)
        return override
    return Path.home()


def _platform_base() -> tuple[Path, Path]:
    """(config_dir, data_dir) di piattaforma. Pura, senza mkdir e senza override."""
    import os
    import sys

    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "CarpeDiem"
        return base, base
    if sys.platform == "win32":
        roaming = os.environ.get("APPDATA", "").strip()
        local = os.environ.get("LOCALAPPDATA", "").strip()
        cfg = (
            Path(roaming) / "CarpeDiem"
            if roaming
            else Path.home() / "AppData" / "Roaming" / "CarpeDiem"
        )
        dat = Path(local) / "CarpeDiem" if local else cfg
        return cfg, dat
    xdg_cfg = os.environ.get("XDG_CONFIG_HOME", "").strip()
    xdg_data = os.environ.get("XDG_DATA_HOME", "").strip()
    cfg = (
        Path(xdg_cfg).expanduser() / "carpediem"
        if xdg_cfg
        else Path.home() / ".config" / "carpediem"
    )
    dat = (
        Path(xdg_data).expanduser() / "carpediem"
        if xdg_data
        else Path.home() / ".local" / "share" / "carpediem"
    )
    return cfg, dat


def config_dir() -> Path:
    """Directory di configurazione (override o default di piattaforma)."""
    override = home_override()
    return override if override is not None else _platform_base()[0]


def data_dir() -> Path:
    """Directory dati (override o default di piattaforma)."""
    override = home_override()
    return override if override is not None else _platform_base()[1]


def base_dir() -> Path:
    """Base dati effettiva: override se impostato, altrimenti data_dir()."""
    override = home_override()
    return override if override is not None else _platform_base()[1]


def backup_dir() -> Path:
    """Directory degli snapshot zip (sotto data_dir, mai legacy)."""
    return data_dir() / "backups"


def config_file() -> Path:
    return config_dir() / "config.json"


def todos_file() -> Path:
    return data_dir() / "todos.json"


def templates_file() -> Path:
    return data_dir() / "templates.json"


def pomodoro_file() -> Path:
    return data_dir() / "pomodoro.json"


def archive_file() -> Path:
    return data_dir() / "archive.json"


def executions_file() -> Path:
    return data_dir() / "executions.json"


def outlook_token_file() -> Path:
    return data_dir() / "outlook-token.json"


# Alias di compatibilita' (import-time, come prima): i writer usano le
# funzioni sopra; le costanti restano per lettori esterni, re-export in
# main e seam di test (conftest tmp_files). Non sono la source of truth.
DATA_FILE = todos_file()
TEMPLATE_FILE = templates_file()
CONFIG_FILE = config_file()
POMODORO_FILE = pomodoro_file()
ARCHIVE_FILE = archive_file()
EXECUTIONS_FILE = executions_file()
OUTLOOK_TOKEN_FILE = outlook_token_file()
BACKUP_DIR = backup_dir()


def load_todos() -> list[TodoItem]:
    todos: list[TodoItem] = []
    for item in _read_dict_list(todos_file()):
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
        todos_file(),
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


def save_todos_synced(
    current: list[dict], base: list[dict], *, force_rewrite: bool = False
) -> list[dict]:
    """Merge three-way sotto lock unico (lettura+merge+scrittura atomici).

    Fail-closed: disco UNREADABLE (envelope non decifrabile) o CORRUPT
    (malformato/shape errata) -> StorageUnreadable, nessuna scrittura.
    Opt-in force_rewrite=True SOLO per il cambio password (_rewrite_all_state):
    memoria autorevole con chiave appena verificata; bypassa UNREADABLE
    (mai CORRUPT: con disco corrotto la memoria non e' autorevole).
    Se il disco e' cifrato ma non decifrabile con la chiave corrente (es. cambio
    password in corso), la memoria e' l'unica fonte di verita': si riscrive
    com'e', senza merge (l'eventuale file precedente resta in `.bak.json`)."""
    with _locked(todos_file()):
        state = _disk_state(todos_file())
        if state == "UNREADABLE" and not force_rewrite:
            raise StorageUnreadable(
                f"File non leggibile, scrittura rifiutata: {todos_file().name}"
            )
        if state == "CORRUPT":
            raise StorageUnreadable(
                f"File non valido, scrittura rifiutata: {todos_file().name}"
            )
        if _is_crypto_unreadable(todos_file()):
            merged = current
        else:
            disk = _read_dict_list(todos_file())
            merged = merge_todo_dicts(base, disk, current)
        _write_locked(todos_file(), _dump_state_text(merged), with_bak=True)
        return merged


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
    if not templates_file().exists():
        return _default_templates()
    try:
        if not templates_file().read_text(encoding="utf-8").strip():
            return _default_templates()  # 0-byte: mai scritto, niente backup
        data = _read_state_file(templates_file())
    except (json.JSONDecodeError, OSError, ValueError):
        _backup_corrupt(templates_file())
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


def save_templates(
    templates: dict[str, list[dict]], *, force_rewrite: bool = False
) -> None:
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
    _write_atomic(
        templates_file(),
        _dump_state_text(serializable),
        guard="dict",
        force_rewrite=force_rewrite,
    )


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
    if not config_file().exists():
        return cfg
    try:
        data = json.loads(config_file().read_text(encoding="utf-8"))
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
    _write_atomic(
        config_file(), json.dumps(payload, indent=2, ensure_ascii=False), guard="dict"
    )


def save_outlook_token(cache_str: str) -> None:
    """Cache token MSAL su file dedicato 0600, envelope cifrato se lock attivo.

    Mai nei backup zip (file escluso da `_backup_sources` per disegno +
    test guardrail), mai nei log. Scrittura atomica come gli altri file.
    """
    import os

    _write_atomic(outlook_token_file(), _dump_state_text({"cache": cache_str}))
    try:
        os.chmod(outlook_token_file(), 0o600)
    except OSError:
        pass


def load_outlook_token() -> str | None:
    """Cache token serializzata, o None (assente, illeggibile, lock spento).

    Envelope cifrato senza chiave -> None (fail-closed, mai plaintext
    di ripiego): con lock spento il fetch e' bloccato dal gate in app.
    """
    if not outlook_token_file().exists():
        return None
    try:
        obj = _read_state_file(outlook_token_file())
    except (json.JSONDecodeError, OSError, ValueError):
        return None
    if not isinstance(obj, dict) or not isinstance(obj.get("cache"), str):
        return None
    return obj["cache"]


def delete_outlook_token() -> None:
    """Revoca locale: cancella il file token (disconnessione)."""
    try:
        outlook_token_file().unlink(missing_ok=True)
    except OSError:
        pass


def load_archive() -> list[dict]:
    if not archive_file().exists():
        return []
    try:
        if not archive_file().read_text(encoding="utf-8").strip():
            return []  # 0-byte: mai scritto, niente backup
        data = _read_state_file(archive_file())
    except (json.JSONDecodeError, OSError, ValueError):
        _backup_corrupt(archive_file())
        return []
    return [d for d in data] if isinstance(data, list) else []


def save_archive(items: list[dict], *, force_rewrite: bool = False) -> None:
    _write_atomic(
        archive_file(),
        _dump_state_text(items),
        guard="list",
        force_rewrite=force_rewrite,
    )


BACKUP_KEEP = 14


def _backup_sources() -> tuple[tuple[str, Path], ...]:
    return (
        ("todos", todos_file()),
        ("templates", templates_file()),
        ("pomodoro", pomodoro_file()),
        ("config", config_file()),
        ("archive", archive_file()),
    )


def list_snapshots() -> list[Path]:
    """Snapshot nuovi (`carpediem_*`) + legacy (`tasko_*`, migrati o storici).

    Entrambi restano ripristinabili via restore_snapshot(); il prune invece
    tocca solo i nuovi (mai cancellare archivi legacy).
    """
    try:
        files = sorted(backup_dir().glob(f"{NEW_BACKUP_PREFIX}*.zip"), reverse=True)
        files += sorted(backup_dir().glob(f"{LEGACY_BACKUP_PREFIX}*.zip"), reverse=True)
    except OSError:
        return []
    return [p for p in files if p.is_file()]


def _snapshot_manifest(files: dict[str, int]) -> dict:
    return {
        "app": "carpediem",
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "files": files,
    }


def create_backup() -> Path:
    """Crea uno snapshot zip di tutti i file di stato + manifest. Ritorna il path."""
    import os
    import zipfile

    backup_dir().mkdir(parents=True, exist_ok=True)
    try:
        # Owner-only quando supportato (POSIX); su Windows no-op senza rompere.
        os.chmod(backup_dir(), 0o700)
    except OSError:
        pass
    # Microsecondi + contatore anti-collisione: due backup nello stesso
    # istante non devono mai sovrascriversi (ZipFile(out, "w") tronca).
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    out = backup_dir() / f"{NEW_BACKUP_PREFIX}{ts}.zip"
    n = 0
    while out.exists():
        n += 1
        out = backup_dir() / f"{NEW_BACKUP_PREFIX}{ts}_{n}.zip"
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
    try:
        # Owner-only quando supportato (POSIX); su Windows no-op senza rompere.
        os.chmod(out, 0o600)
    except OSError:
        pass
    prune_snapshots()
    return out


def prune_snapshots(keep: int = BACKUP_KEEP) -> None:
    """Potatura retention: solo snapshot NUOVI. I legacy non si cancellano mai qui."""
    try:
        files = sorted(backup_dir().glob(f"{NEW_BACKUP_PREFIX}*.zip"), reverse=True)
    except OSError:
        return
    for old in [p for p in files if p.is_file()][keep:]:
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
    if not pomodoro_file().exists():
        return cfg
    try:
        if not pomodoro_file().read_text(encoding="utf-8").strip():
            return cfg  # 0-byte: mai scritto, niente backup
        data = _read_state_file(pomodoro_file())
    except (json.JSONDecodeError, OSError, ValueError):
        _backup_corrupt(pomodoro_file())
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


def save_pomodoro(state: dict, *, force_rewrite: bool = False) -> None:
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
    _write_atomic(
        pomodoro_file(),
        _dump_state_text(payload),
        guard="dict",
        force_rewrite=force_rewrite,
    )


# Cap anti-crescita infinita: oltre si scartano i piu' vecchi in scrittura.
MAX_EXECUTIONS = 5000


def load_executions() -> list[TaskExecution]:
    """History delle esecuzioni (M2). File assente/vuoto/corrotto -> [].

    Nessuna migrazione richiesta: un'installazione senza history si comporta
    come prima (nessuna calibrazione disponibile).
    """
    return [TaskExecution.from_dict(d) for d in _read_dict_list(executions_file())]


def save_executions(items: list, *, force_rewrite: bool = False) -> None:
    """Riscrive l'intera history (solo password rotation: snapshot
    pre-rotazione + force_rewrite, mai uso normale che e' append-only).
    Stesse garanzie di append: lock singolo, cap, guard fail-closed."""
    raw = []
    for e in items or []:
        if isinstance(e, TaskExecution):
            raw.append(e.to_dict())
        elif isinstance(e, dict):
            raw.append(e)
    dicts = [d for d in raw if isinstance(d, dict)]
    with _locked(executions_file()):
        if not force_rewrite:
            _ensure_writable(executions_file())
        if len(dicts) > MAX_EXECUTIONS:
            dicts = dicts[-MAX_EXECUTIONS:]
        _write_locked(executions_file(), _dump_state_text(dicts))


def append_execution(exec: TaskExecution | dict) -> TaskExecution:
    """Aggiunge un record alla history sotto un solo lock (append-only).

    Idempotente su (task_id, ended_at): un record con stessa coppia non viene
    duplicato (ritorna quello esistente). Oltre MAX_EXECUTIONS si scartano i
    piu' vecchi. Ritorna il record registrato.
    """
    item = (
        exec
        if isinstance(exec, TaskExecution)
        else TaskExecution.from_dict(exec if isinstance(exec, dict) else {})
    )
    with _locked(executions_file()):
        _ensure_writable(executions_file())
        items = [TaskExecution.from_dict(d) for d in _read_dict_list(executions_file())]
        if item.task_id is not None and item.ended_at:
            for known in items:
                if known.task_id == item.task_id and known.ended_at == item.ended_at:
                    return known
        items.append(item)
        if len(items) > MAX_EXECUTIONS:
            items = items[-MAX_EXECUTIONS:]
        _write_locked(executions_file(), _dump_state_text([e.to_dict() for e in items]))
    return item


# --- Migrazione legacy -----------------------------------------------------
#
# Sorgenti legacy (sola lettura): ~/.todo_*.json + ~/Tasko_backups/tasko_*.zip
# (con TASKO_HOME attiva, la base legacy e' quella dell'override).
# Policy: copia byte-identica verificata verso i nuovi path; il nuovo
# esistente vince sempre (mai sovrascrittura/merge); il legacy non viene
# MAI cancellato; fail-closed per file (errori raccolti nel report, target
# parziali rimossi, legacy intatto). Mai eseguita all'import: parte
# dall'inizializzazione controllata (main()), mai dai test salvo chiamata
# esplicita.

# (kind, nome legacy, target, shape attesa per la verifica)
_LEGACY_MAP: tuple[tuple[str, str, _Callable[[], Path], str], ...] = (
    ("todos", ".todo_app.json", todos_file, "list"),
    ("templates", ".todo_templates.json", templates_file, "dict"),
    ("config", ".todo_config.json", config_file, "dict"),
    ("pomodoro", ".todo_pomodoro.json", pomodoro_file, "dict"),
    ("archive", ".todo_archive.json", archive_file, "list"),
    ("executions", ".todo_executions.json", executions_file, "list"),
    ("outlook_token", ".todo_outlook_token.json", outlook_token_file, "any"),
)


def _legacy_candidate_bases() -> list[Path]:
    """Basi in cui cercare dati legacy. Con override attivo si guarda SOLO
    nelle dir di override (mai nella home reale: un test con HOME temporanea
    non deve importare i dati veri dell'utente); senza override, la home."""
    import os

    if _env_first(ENV_HOME_NEW, ENV_HOME_LEGACY):
        bases: list[Path] = []
        for var in (ENV_HOME_NEW, ENV_HOME_LEGACY):
            val = os.environ.get(var, "").strip()
            if val:
                p = Path(val).expanduser()
                if p not in bases:
                    bases.append(p)
        return bases
    return [Path.home()]


def _verify_state_bytes(raw: bytes, expect: str) -> bool:
    """True se i byte sono migrabili: JSON valido con shape attesa, oppure
    envelope ben formato ma non decifrabile con la chiave corrente (chiave
    errata/assente: copia cieca byte-identica, mai interpretare ne' scartare
    — l'app manterra' lo stesso comportamento fail-closed di prima).

    Mai eccezioni. Mai backup .corrotto da qui: un envelope non decifrabile
    non e' evidenza di corruzione.
    """
    try:
        text = raw.decode("utf-8")
    except ValueError:
        return False
    if not text.strip():
        return False
    try:
        is_env = _crypto.is_envelope(text)
    except Exception:
        return False
    try:
        obj, _ = _crypto.unprotect_text(text)
    except Exception:
        return is_env
    if expect == "list" and not isinstance(obj, list):
        return False
    if expect == "dict" and not isinstance(obj, dict):
        return False
    return True


def _migrate_one_file(kind: str, src: Path, target: Path, expect: str) -> str:
    """Copia un singolo file legacy. Ritorna l'esito per il report.

    Esiti: "migrated" | "skipped_target_exists" | "skipped_no_legacy" |
    "skipped_invalid:<motivo>" (mai eccezioni: gli errori I/O diventano
    "skipped_error:<motivo>", legacy intatto, target parziale rimosso).
    """
    if target.exists():
        return "skipped_target_exists"
    if not src.exists():
        return "skipped_no_legacy"
    try:
        raw = src.read_bytes()
    except OSError as exc:
        return f"skipped_error:lettura legacy: {exc}"
    if not raw.strip():
        return "skipped_no_legacy"  # 0-byte: mai scritto, niente da migrare
    if not _verify_state_bytes(raw, expect):
        return "skipped_invalid:legacy non leggibile, ignorato senza toccarlo"
    try:
        _write_atomic(
            target,
            raw.decode("utf-8"),
            guard=expect if expect in ("list", "dict") else None,
        )
    except OSError as exc:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        return f"skipped_error:scrittura: {exc}"
    try:
        back = target.read_bytes()
    except OSError as exc:
        return f"skipped_error:rilettura: {exc}"
    if back != raw or not _verify_state_bytes(back, expect):
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        return "skipped_error:verifica fallita, target rimosso"
    return "migrated"


def _migrate_one_backup(zpath: Path) -> str:
    """Copia un singolo zip legacy byte-identico (manifest storici intoccati)."""
    import zipfile

    dest = backup_dir() / zpath.name
    if dest.exists():
        return "skipped_target_exists"
    try:
        raw = zpath.read_bytes()
    except OSError as exc:
        return f"skipped_error:lettura zip: {exc}"
    try:
        import io

        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            if zf.testzip() is not None:
                return "skipped_invalid:zip danneggiato, ignorato senza toccarlo"
    except Exception as exc:
        return f"skipped_invalid:zip illeggibile ({exc}), ignorato senza toccarlo"
    try:
        with _locked(dest):
            _write_bytes_locked(dest, raw)
    except OSError as exc:
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            pass
        return f"skipped_error:scrittura zip: {exc}"
    try:
        ok = dest.read_bytes() == raw
    except OSError:
        ok = False
    if not ok:
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            pass
        return "skipped_error:verifica zip fallita, target rimosso"
    return "migrated"


def migrate_legacy() -> dict[str, list[str]]:
    """Migra i dati legacy verso i nuovi path. Idempotente, mai distruttiva.

    Ritorna un report {kind: [dettagli]} con chiavi "migrated",
    "skipped_target_exists", "skipped_no_legacy", "skipped_*", "backups".
    Il legacy non viene mai cancellato ne' modificato; il target esistente
    non viene mai sovrascritto; gli errori sono voci di report, non crash.
    """
    report: dict[str, list[str]] = {
        "migrated": [],
        "skipped_target_exists": [],
        "skipped_no_legacy": [],
        "skipped_invalid": [],
        "skipped_error": [],
        "backups": [],
    }
    for base in _legacy_candidate_bases():
        for kind, lname, target_fn, expect in _LEGACY_MAP:
            target = target_fn()
            outcome = _migrate_one_file(kind, base / lname, target, expect)
            if outcome == "migrated":
                report["migrated"].append(kind)
            elif outcome == "skipped_target_exists":
                if kind not in report["skipped_target_exists"]:
                    report["skipped_target_exists"].append(kind)
            elif outcome == "skipped_no_legacy":
                if kind not in report["skipped_no_legacy"]:
                    report["skipped_no_legacy"].append(kind)
            elif outcome.startswith("skipped_invalid"):
                report["skipped_invalid"].append(f"{kind}: {outcome}")
            else:
                report["skipped_error"].append(f"{kind}: {outcome}")
        try:
            zips = sorted((base / LEGACY_BACKUP_DIRNAME).glob("tasko_*.zip"))
        except OSError:
            zips = []
        for zpath in zips:
            if not zpath.is_file():
                continue
            outcome = _migrate_one_backup(zpath)
            if outcome == "migrated":
                report["backups"].append(zpath.name)
    return report
