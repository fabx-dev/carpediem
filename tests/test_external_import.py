"""Sorgenti esterne Fase 8: identita' (source, external_id), import idempotente."""

from datetime import datetime

from src.models import TodoItem
from src.planner import Planner, schedule
from src.planner.models import TimeWindow
from tests.conftest import make_app, make_todo


def _csv(path, rows):
    import csv

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "titolo", "stato", "source", "external_id"])
        w.writerows(rows)


def test_modello_default_e_normalizzazione():
    t = TodoItem("T")
    assert (t.source, t.external_id) == ("", "")
    t = TodoItem("T", source=" CSV ", external_id=" 42 ")
    assert (t.source, t.external_id) == ("csv", "42")
    back = TodoItem.from_dict(t.to_dict())
    assert (back.source, back.external_id) == ("csv", "42")
    old = TodoItem.from_dict({"id": 1, "title": "V"})
    assert (old.source, old.external_id) == ("", "")  # file vecchi


def test_store_by_external(tmp_files):
    app = make_app([make_todo("A", todo_id=1, source="csv", external_id="10")])
    got = app.store.by_external("csv", "10")
    assert got is not None and got.id == 1
    assert app.store.by_external("CSV", "10") is got  # source case-insensitive
    assert app.store.by_external("other", "10") is None
    assert app.store.by_external("csv", "") is None
    assert app.store.by_external("", "") is None


def test_import_idempotente_e_sorgenti_distinte(tmp_files):
    app = make_app([])
    path = tmp_files / "ext.csv"
    _csv(path, [[7, "Sette", "attivo", "todoist", "x1"]])
    n1, _ = app._import_csv_file(str(path))
    assert n1 == 1
    first_id = app.todos[0].id
    assert (app.todos[0].source, app.todos[0].external_id) == ("todoist", "x1")
    n2, sk2 = app._import_csv_file(str(path))  # stesso record
    assert (n2, len(app.todos)) == (0, 1)
    assert sk2 == 1 and app.todos[0].id == first_id  # id interno invariato
    # Stesso external_id, source diversa -> task distinto.
    _csv(path, [[7, "Sette", "attivo", "trello", "x1"]])
    n3, _ = app._import_csv_file(str(path))
    assert n3 == 1 and len(app.todos) == 2


def test_senza_external_id_sempre_nuovo_e_mix_errori(tmp_files):
    app = make_app([])
    path = tmp_files / "noext.csv"
    _csv(path, [["", "Uno", "attivo", "", ""], ["", "", "attivo", "", ""]])
    n1, sk1 = app._import_csv_file(str(path))
    assert (n1, sk1) == (1, 1)  # uno creato, uno senza titolo scartato
    n2, _ = app._import_csv_file(str(path))
    assert n2 == 1 and len(app.todos) == 2  # esplicito: reimporta come nuovo


def test_importato_in_planner_e_scheduler(tmp_files):
    app = make_app([])
    path = tmp_files / "ext.csv"
    _csv(path, [[3, "Pianificami", "attivo", "csv", "3"]])
    app._import_csv_file(str(path))
    plan = Planner(app.todos, today="2026-09-10").propose()
    assert [i.todo_id for i in plan.planned] == [app.todos[0].id]
    sched = schedule(
        plan,
        [TimeWindow(datetime(2026, 9, 10, 9), datetime(2026, 9, 10, 18))],
    )
    assert [s.item.todo_id for s in sched.scheduled] == [app.todos[0].id]
    # Il Planner non distingue: stesso task senza source, stesso risultato.
    plain = [make_todo("Pianificami", todo_id=99)]
    assert (
        Planner(plain, today="2026-09-10").propose().to_legacy()[0][1:]
        == (plan.to_legacy()[0][1:])
    )
