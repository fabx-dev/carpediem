"""Interfaccia riga di comando non interattiva."""

import argparse
import sys
from datetime import datetime

from src.lang import T, get_lang
from src.models import Priority, TodoItem, _is_valid_date, _normalize_date
from src.nlparse import parse
from src.storage import load_todos
from src.store import TodoStore


def _cli_parse_priority(value: str | None) -> Priority:
    v = (value or "media").strip().lower()
    mapping = {
        "alta": Priority.HIGH,
        "high": Priority.HIGH,
        "h": Priority.HIGH,
        "media": Priority.MEDIUM,
        "medium": Priority.MEDIUM,
        "m": Priority.MEDIUM,
        "bassa": Priority.LOW,
        "low": Priority.LOW,
        "l": Priority.LOW,
    }
    return mapping.get(v, Priority.MEDIUM)


def _cli_state_filter(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().lower()
    mapping = {
        "attivo": "attivo",
        "active": "attivo",
        "sospeso": "in_sospeso",
        "in_sospeso": "in_sospeso",
        "paused": "in_sospeso",
        "completato": "completato",
        "completati": "completato",
        "done": "completato",
    }
    return mapping.get(v)


def _cli_main(argv: list[str]) -> int:
    """CLI non interattiva: carpediem add|list|done|show. Ritorna exit code."""

    parser = argparse.ArgumentParser(prog="carpediem", description="CarpeDiem CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_add = sub.add_parser("add", help=T("cli_add_h"))
    p_add.add_argument("title", help=T("cli_title_h"))
    p_add.add_argument("--project", default="", help=T("cli_proj_h"))
    p_add.add_argument("--due", default="", help=T("cli_due_h"))
    p_add.add_argument("--priority", default="media", help=T("cli_prio_h"))
    p_add.add_argument("--tags", default="", help=T("cli_tags_h"))
    p_list = sub.add_parser("list", help=T("cli_list_h"))
    p_list.add_argument("--state", default=None, help=T("cli_state_h"))
    p_list.add_argument("--project", default=None, help=T("cli_projf_h"))
    p_list.add_argument(
        "--porcelain",
        action="store_true",
        help=T("cli_porc_h"),
    )
    p_done = sub.add_parser("done", help=T("cli_done_h"))
    p_done.add_argument("id", type=int, help=T("cli_id_h"))
    p_show = sub.add_parser("show", help=T("cli_show_h"))
    p_show.add_argument("id", type=int, help=T("cli_id_h"))
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)

    def err(msg: str) -> None:
        print(f"carpediem: {msg}", file=sys.stderr)

    if args.cmd == "add":
        classic = bool(
            args.project or args.due or args.tags or args.priority != "media"
        )
        if classic:
            # Modalita' classica: titolo alla lettera, flag espliciti.
            title = args.title.strip()
            if not title:
                err(T("cli_empty_title"))
                return 2
            due = _normalize_date(args.due) if args.due else ""
            if args.due and not _is_valid_date(due):
                err(T("cli_bad_date", d=args.due))
                return 2
            todo = TodoItem(
                title=title,
                priority=_cli_parse_priority(args.priority),
                due=due,
                project=(args.project or "").strip().lower(),
                tags=[
                    t.strip().lower() for t in (args.tags or "").split(",") if t.strip()
                ],
            )
        else:
            # Modalita' NL: tutti i campi dalla frase, flag assenti.
            res = parse(args.title, get_lang())
            title = res["title"].strip()
            if not title:
                err(T("cli_empty_title"))
                return 2
            todo = TodoItem(
                title=title,
                priority=res["priority"],
                due=res["due"],
                project=res["project"],
                tags=res["tags"],
                recurrence=res["recurrence"],
                stima_pomo=res["stima_pomo"],
            )
        store = TodoStore.load()
        store.add(todo)
        store.commit()
        print(todo.id)
        return 0

    if args.cmd == "list":
        state = _cli_state_filter(args.state)
        if args.state and state is None:
            err(T("cli_bad_state", s=args.state))
            return 2
        rows = []
        for t in load_todos():
            if state is not None and t.state != state:
                continue
            if args.project is not None and t.project != args.project.strip().lower():
                continue
            rows.append(t)
        rows.sort(key=lambda t: (t.due or "9999", t.title.lower()))
        for t in rows:
            if args.porcelain:
                print(f"{t.id}|{t.state}|{t.priority.value}|{t.due or '-'}|{t.title}")
            else:
                mark = "X" if t.done else ("P" if t.paused else "O")
                proj = f" @{t.project}" if t.project else ""
                print(
                    T(
                        "cli_row",
                        id=t.id,
                        m=mark,
                        t=t.title,
                        p=proj,
                        d=t.due or "-",
                        r=t.priority.value,
                    )
                )
        return 0

    if args.cmd == "done":
        store = TodoStore.load()
        target = store.by_id(args.id)
        if target is None:
            err(T("cli_notfound", id=args.id))
            return 1
        if target.done:
            print(target.id)
            return 0
        target.done = True
        target.paused = False
        target.planned_for = ""
        target.completed_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        store.commit()
        print(target.id)
        return 0
    todos = load_todos()
    target = next((t for t in todos if t.id == args.id), None)
    if target is None:
        err(T("cli_notfound", id=args.id))
        return 1
    # show
    lines = [
        f"#{target.id} {target.title}",
        T(
            "cli_show_line",
            s=target.state,
            p=target.priority.value,
            d=target.due or "-",
        ),
    ]
    if target.project:
        lines.append(T("cli_proj_lab", p=target.project))
    if target.tags:
        lines.append(T("cli_tags_lab", t=", ".join(target.tags)))
    if target.notes:
        lines.append(T("cli_notes_lab", n=target.notes))
    lines.append(T("cli_pomo_lab", n=target.pomodoros))
    print("\n".join(lines))
    return 0
