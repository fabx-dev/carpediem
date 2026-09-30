"""Import CSV puro dal filesystem (estratto da TodoApp, E4).

Unico I/O: lettura del file CSV. Lo store e' iniettato (niente App, niente
Textual, niente planner). Ritorna (importati, scartati); la persistenza
(commit) resta al chiamante. Comportamento identico all'originale, inclusa
l'idempotenza (source, external_id) della Fase 8.
"""

import csv
from datetime import datetime
from pathlib import Path

from src.models import Priority, TodoItem, _normalize_date
from src.store import TodoStore


def import_csv_file(path: str, store: TodoStore) -> tuple[int, int]:
    """Importa task da CSV (formato export o compatibile). Ritorna (importati, scartati)."""
    p = Path(str(path).strip()).expanduser()
    pr_map = {
        "alta": Priority.HIGH,
        "high": Priority.HIGH,
        "media": Priority.MEDIUM,
        "medium": Priority.MEDIUM,
        "bassa": Priority.LOW,
        "low": Priority.LOW,
    }
    with open(p, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return 0, 0
        cols = {c.strip().lower(): c for c in reader.fieldnames if c and c.strip()}

        def col(*names: str) -> str:
            for n in names:
                if n in cols:
                    v = reader_row.get(cols[n])
                    return str(v or "").strip()
            return ""

        raw_rows: list[dict | None] = []
        for reader_row in reader:
            if not isinstance(reader_row, dict):
                continue
            title = col("titolo", "title", "name", "task")
            if not title:
                raw_rows.append(None)
                continue
            state = col("stato", "state", "status").lower()
            priority = pr_map.get(col("priorita", "priority").lower(), Priority.MEDIUM)
            tags_raw = col("tags", "tag", "etichette")
            tags = [
                t.strip().lower()
                for t in tags_raw.replace(";", ",").split(",")
                if t.strip()
            ]
            try:
                pomodoros = int(col("pomodori", "pomodoros") or 0)
            except (ValueError, TypeError):
                pomodoros = 0
            try:
                stima = max(0, int(col("stima_pomo", "stima", "estimate") or 0))
            except (ValueError, TypeError):
                stima = 0
            try:
                old_parent = int(col("padre", "parent_id", "parent") or 0) or None
            except (ValueError, TypeError):
                old_parent = None
            try:
                old_id = int(col("id") or 0) or None
            except (ValueError, TypeError):
                old_id = None
            # Identita' esterna (Fase 8): colonna dedicata o fallback
            # all'id del file (tipico del nostro export); senza ID
            # il record non ha identita' -> sempre nuovo, mai dedup.
            raw_ext = col("external_id", "externalid", "id_esterno")
            external_id = raw_ext or (str(old_id) if old_id is not None else "")
            raw_rows.append(
                {
                    "old_id": old_id,
                    "source": col("source", "sorgente") or "csv",
                    "external_id": external_id,
                    "title": title,
                    "priority": priority,
                    "done": state
                    in ("completato", "completed", "done", "x", "true", "1"),
                    "paused": state in ("in_sospeso", "sospeso", "paused", "suspended"),
                    "due": _normalize_date(col("scadenza", "due", "deadline")),
                    "notes": col("note", "notes", "descrizione"),
                    "project": col("progetto", "project"),
                    "tags": tags,
                    "created": col("creazione", "created"),
                    "completed_at": col("completato_il", "completed_at")[:16],
                    "pomodoros": pomodoros,
                    "stima_pomo": stima,
                    "old_parent": old_parent,
                }
            )
    # Rimappa gli id (padri compresi) sui nuovi.
    id_map: dict[int, int] = {}
    created: list[TodoItem] = []
    pending_parents: list = []
    skipped = 0
    for raw in raw_rows:
        if raw is None:
            skipped += 1
            continue
        assert raw is not None
        # Idempotenza (Fase 8): stessa (source, external_id) -> niente
        # duplicato; l'id interno resta invariato, niente merge.
        # Senza external_id il record e' sempre nuovo (esplicito).
        existing = store.by_external(raw["source"], raw["external_id"])
        if existing is not None:
            if raw["old_id"] is not None and existing.id is not None:
                id_map[raw["old_id"]] = existing.id
            skipped += 1
            continue
        nid = store.allocate_id()
        ext = raw["external_id"]
        todo = TodoItem(
            title=raw["title"],
            priority=raw["priority"],
            done=raw["done"],
            paused=raw["paused"] and not raw["done"],
            created=raw["created"] or datetime.now().strftime("%Y-%m-%d %H:%M"),
            due=raw["due"],
            notes=raw["notes"],
            project=raw["project"],
            tags=raw["tags"],
            completed_at=raw["completed_at"] if raw["done"] else "",
            pomodoros=raw["pomodoros"],
            stima_pomo=raw.get("stima_pomo", 0),
            source=raw["source"] if ext else "",
            external_id=ext,
            todo_id=nid,
        )
        if raw["old_id"] is not None:
            id_map[raw["old_id"]] = nid
        pending_parents.append(raw["old_parent"])
        created.append(todo)
    for todo, old_parent in zip(created, pending_parents):
        if old_parent is not None and old_parent in id_map:
            todo.parent_id = id_map[old_parent]
    store.add_many(created)
    return len(created), skipped
