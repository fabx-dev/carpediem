"""Test TodoStore: id, lookup, mutazioni, commit unico."""

import src.main as m
from src.store import TodoStore
from tests.conftest import make_app, make_todo


def test_add_assegna_id_sequenziali():
    s = TodoStore()
    a = s.add(make_todo("A", todo_id=None))
    b = s.add(make_todo("B", todo_id=None))
    assert (a.id, b.id) == (1, 2)
    assert s.next_id == 3


def test_add_tiene_id_libero_riassegna_collisioni():
    s = TodoStore([make_todo("A", todo_id=5)])
    libero = s.add(make_todo("B", todo_id=7))
    assert libero.id == 7
    doppio = s.add(make_todo("C", todo_id=5))
    assert doppio.id == 8  # 5 occupato -> nuovo id
    assert s.next_id == 9


def test_allocate_consuma():
    s = TodoStore([make_todo("A", todo_id=3)])
    assert s.allocate_id() == 4
    assert s.next_id == 5


def test_lookup_e_gerarchia():
    s = TodoStore(
        [
            make_todo("P", todo_id=1),
            make_todo("F1", todo_id=2, parent_id=1),
            make_todo("F2", todo_id=3, parent_id=1),
            make_todo("N", todo_id=4, parent_id=2),
            make_todo("Orfano", todo_id=5, parent_id=999),
        ]
    )
    assert s.by_id(2).title == "F1"
    assert s.by_id(999) is None and s.by_id(None) is None
    assert not s.has_id(999) and s.has_id(1)
    assert [t.id for t in s.children(1)] == [2, 3]
    assert [t.id for t in s.descendants(1)] == [2, 4, 3]
    assert s.depth(s.by_id(4)) == 2
    assert s.depth(s.by_id(1)) == 0
    assert s.depth(s.by_id(5)) == 0  # parent mancante: si ferma


def test_remove_ids_ordine_e_indice():
    s = TodoStore(
        [
            make_todo("A", todo_id=1),
            make_todo("B", todo_id=2),
            make_todo("C", todo_id=3),
        ]
    )
    removed = s.remove_ids({3, 1})
    assert [t.title for t in removed] == ["A", "C"]
    assert [t.title for t in s.all()] == ["B"]
    assert s.by_id(1) is None and s.by_id(2).title == "B"
    assert s.next_id == 4  # il contatore non arretra mai


def test_replace_all_reindicizza():
    s = TodoStore([make_todo("A", todo_id=1)])
    s.replace_all([make_todo("X", todo_id=10), make_todo("Y", todo_id=20)])
    assert s.by_id(10).title == "X" and s.by_id(1) is None
    assert s.next_id == 21


def test_parent_ciclici_non_bloccano():
    a = make_todo("A", todo_id=1, parent_id=2)
    b = make_todo("B", todo_id=2, parent_id=1)
    s = TodoStore([a, b])
    assert s.depth(a) == 1  # si ferma al ciclo, non loop infinito
    assert sorted(t.id for t in s.descendants(1)) == [
        1,
        2,
    ]  # termina, niente ricorsione infinita


def test_created_mancante_non_viene_inventato(tmp_files):
    import json

    m.DATA_FILE.write_text(json.dumps([{"id": 1, "title": "Legacy"}]))
    s = TodoStore.load()
    assert s.by_id(1).created == ""
    s.commit()  # load+save non deve sporcare i dati storici
    assert TodoStore.load().by_id(1).created == ""


def test_add_assegna_created_ai_nuovi():
    s = TodoStore()
    t = s.add(make_todo("N", todo_id=None))
    assert t.created  # timestamp reale assegnato all'inserimento


def test_commit_e_reload_tmp(tmp_files):
    s = TodoStore([make_todo("A", todo_id=1, project="lav")])
    s.commit()
    assert [t.title for t in TodoStore.load().all()] == ["A"]
    # modifica esterna -> reload la vede
    m._save_todos_plain([make_todo("B", todo_id=2)])
    s.reload()
    assert [t.title for t in s.all()] == ["B"]
    assert s.next_id == 3


def test_app_todos_e_next_id_restano_sincronizzati(tmp_files):
    app = make_app([make_todo("A", todo_id=1)])
    assert app.next_id == 2 and app.store.by_id(1).title == "A"
    app.todos = [make_todo("X", todo_id=9)]
    assert app.store.by_id(9).title == "X" and app.next_id == 10
    app.next_id = 50
    assert app.store.allocate_id() == 50


def test_app_save_data_scrive_lo_store(tmp_files):
    app = make_app([make_todo("A", todo_id=1)])
    app.store.add(make_todo("B", todo_id=None))
    app._save_data()
    assert [t.title for t in m.load_todos()] == ["A", "B"]


def test_plain_mai_in_produzione():
    """B6 guardrail: app/screens/cli scrivono solo via store.commit()."""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "src"
    vietati = []
    for path in [root / "app.py", root / "cli.py", root / "commands.py"]:
        if "_save_todos_plain" in path.read_text(encoding="utf-8"):
            vietati.append(path.name)
    for path in (root / "screens").glob("*.py"):
        if path.name == "__init__.py":
            continue
        if "_save_todos_plain" in path.read_text(encoding="utf-8"):
            vietati.append(f"screens/{path.name}")
    assert vietati == [], f"writer plain in produzione: {vietati}"


def test_commit_skipped_visibile_e_non_perde_validi(tmp_files, monkeypatch):
    """B2: dict non parsabili nel merged contati in last_skipped, validi intatti."""
    import src.store as store_module

    s = TodoStore([make_todo("A", todo_id=1)], base=[])
    reali = [t.to_dict() for t in s.all()]
    monkeypatch.setattr(
        store_module,
        "save_todos_synced",
        lambda current, base, **kw: reali + ["spazzatura", {"id": 2, "title": "B"}],
    )
    s.commit()
    assert s.last_skipped == 1
    assert sorted(t.title for t in s.all()) == ["A", "B"]


def test_undo_con_collisione_riassegna(tmp_files):
    import asyncio

    async def t():
        app = make_app([make_todo("A", todo_id=1)])
        async with app.run_test(size=(120, 40)):
            app._undo_stack.append([make_todo("A2", todo_id=1)])  # id collides
            app.action_undo_delete()
            assert sorted(t.title for t in app.todos) == ["A", "A2"]
            assert sorted(t.id for t in app.todos) == [1, 2]

    asyncio.run(t())
