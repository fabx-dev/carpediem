"""Regression fail-closed Phase 1: unreadable/corrupt mai sovrascritti.

Invariante: failed write => primary (e backup) byte-identici.
Letture restano tolleranti; solo le scritture rifiutano.
"""

import hashlib

import pytest

import src.crypto as crypto_mod
import src.storage as st
from src.crypto import encode_password
from src.models import TodoItem
from src.store import TodoStore


def _md5(p) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def _seed_envelope_todos(pw="segreta12"):
    crypto_mod.set_key(encode_password(pw))
    try:
        st._save_todos_plain([TodoItem(todo_id=1, title="A")])
        return st.DATA_FILE.read_bytes()
    finally:
        crypto_mod.set_key(None)


def _titles(store) -> list:
    return [t.title for t in store.all()]


def test_d1_commit_senza_chiave_non_tocca_envelope():
    prima = _seed_envelope_todos()
    bak = st.DATA_FILE.with_suffix(".bak.json")
    bak_prima = bak.read_bytes() if bak.exists() else None
    s = TodoStore.load()
    assert s.all() == []
    s.add(TodoItem(title="finto"))
    with pytest.raises(st.StorageUnreadable):
        s.commit()
    assert st.DATA_FILE.read_bytes() == prima
    assert (bak.read_bytes() if bak.exists() else None) == bak_prima


def test_d1_commit_chiave_errata_non_tocca_envelope():
    prima = _seed_envelope_todos()
    crypto_mod.set_key(encode_password("sbagliata"))
    try:
        s = TodoStore.load()
        assert s.all() == []
        s.add(TodoItem(title="finto"))
        with pytest.raises(st.StorageUnreadable):
            s.commit()
        assert st.DATA_FILE.read_bytes() == prima
    finally:
        crypto_mod.set_key(None)


def test_d1_non_lista_non_diventa_stato_scrivibile():
    st.DATA_FILE.write_text('{"x": 1}', encoding="utf-8")
    prima = st.DATA_FILE.read_bytes()
    s = TodoStore.load()
    assert s.all() == []
    s.add(TodoItem(title="finto"))
    with pytest.raises(st.StorageUnreadable):
        s.commit()
    assert st.DATA_FILE.read_bytes() == prima


def test_d1_chiave_errata_non_crea_corrotto():
    _seed_envelope_todos()
    crypto_mod.set_key(encode_password("sbagliata"))
    try:
        assert TodoStore.load().all() == []
    finally:
        crypto_mod.set_key(None)
    assert not st.DATA_FILE.with_suffix(".corrotto.json").exists()


def test_d2_append_execution_su_envelope_non_tocca_file():
    from src.models import TaskExecution

    crypto_mod.set_key(encode_password("segreta12"))
    try:
        st._write_atomic(
            st.EXECUTIONS_FILE,
            st._dump_state_text(
                [
                    {
                        "task_id": 1,
                        "ended_at": "2026-10-01",
                        "estimate_pomo": 2,
                        "actual_pomo": 2,
                    }
                ]
            ),
        )
        prima = st.EXECUTIONS_FILE.read_bytes()
    finally:
        crypto_mod.set_key(None)
    with pytest.raises(st.StorageUnreadable):
        st.append_execution(
            TaskExecution(task_id=2, ended_at="2026-10-02", estimate_pomo=1)
        )
    assert st.EXECUTIONS_FILE.read_bytes() == prima


def test_d2_save_templates_su_envelope_non_tocca_file():
    crypto_mod.set_key(encode_password("segreta12"))
    try:
        st.save_templates({"t": []})
        prima = st.TEMPLATE_FILE.read_bytes()
        assert crypto_mod.is_envelope(prima.decode("utf-8"))
    finally:
        crypto_mod.set_key(None)
    with pytest.raises(st.StorageUnreadable):
        st.save_templates({"t": [{"title": "x", "priority": "media"}]})
    assert st.TEMPLATE_FILE.read_bytes() == prima


def test_d2_save_archive_su_envelope_non_tocca_file():
    crypto_mod.set_key(encode_password("segreta12"))
    try:
        st.save_archive([{"id": 9, "title": "old"}])
        prima = st.ARCHIVE_FILE.read_bytes()
    finally:
        crypto_mod.set_key(None)
    with pytest.raises(st.StorageUnreadable):
        st.save_archive([{"id": 10, "title": "new"}])
    assert st.ARCHIVE_FILE.read_bytes() == prima


def test_d2_save_pomodoro_su_envelope_non_tocca_file():
    crypto_mod.set_key(encode_password("segreta12"))
    try:
        st.save_pomodoro({"phase": "focus"})
        prima = st.POMODORO_FILE.read_bytes()
    finally:
        crypto_mod.set_key(None)
    with pytest.raises(st.StorageUnreadable):
        st.save_pomodoro({"phase": "break"})
    assert st.POMODORO_FILE.read_bytes() == prima


def test_d5_save_config_su_corrotto_non_tocca_file():
    st.CONFIG_FILE.write_text("{{{rotto", encoding="utf-8")
    prima = st.CONFIG_FILE.read_bytes()
    with pytest.raises(st.StorageUnreadable):
        st.save_config(dict(st.DEFAULT_CONFIG))
    assert st.CONFIG_FILE.read_bytes() == prima


def test_d5_save_templates_shape_errata_non_tocca_file():
    st.TEMPLATE_FILE.write_text("[1, 2]", encoding="utf-8")
    prima = st.TEMPLATE_FILE.read_bytes()
    with pytest.raises(st.StorageUnreadable):
        st.save_templates({"t": []})
    assert st.TEMPLATE_FILE.read_bytes() == prima


def test_d3_cambio_password_conserva_archivio(tmp_files):
    from tests.conftest import make_app, run

    async def t():
        st._save_todos_plain([TodoItem(todo_id=1, title="A")])
        st.save_archive([{"id": 7, "title": "arch"}])
        app = make_app([TodoItem(todo_id=1, title="A")])
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            # enable (da in chiaro): archivio cifrato, intatto
            app._sec_enable(["nuova1234", "nuova1234"])
            await pilot.pause()
            assert crypto_mod.is_unlocked()
            assert st.load_archive() == [{"id": 7, "title": "arch"}]
            # change: stessa garanzia vecchia -> nuova (app resta sbloccata)
            app._sec_change(["nuova1234", "altra1234", "altra1234"])
            await pilot.pause()
            assert st.load_archive() == [{"id": 7, "title": "arch"}]
            assert _titles(TodoStore.load()) == ["A"]
            # disable: archivio torna in chiaro, intatto
            app._sec_disable(["altra1234"])
            await pilot.pause()
            assert not crypto_mod.is_unlocked()
            assert st.load_archive() == [{"id": 7, "title": "arch"}]
            assert _titles(TodoStore.load()) == ["A"]

    run(t())


def test_d3_cambio_password_legittimo_riscrive():
    _seed_envelope_todos(pw="vecchia")
    crypto_mod.set_key(encode_password("vecchia"))
    try:
        s = TodoStore.load()
        assert _titles(s) == ["A"]
    finally:
        crypto_mod.set_key(encode_password("nuova"))
    s.commit(force_rewrite=True)
    crypto_mod.set_key(encode_password("nuova"))
    try:
        assert _titles(TodoStore.load()) == ["A"]
    finally:
        crypto_mod.set_key(None)


def test_d3_stale_senza_force_non_riscrive():
    _seed_envelope_todos(pw="vecchia")
    prima = st.DATA_FILE.read_bytes()
    crypto_mod.set_key(encode_password("nuova"))
    try:
        s = TodoStore.load()
        assert s.all() == []
        with pytest.raises(st.StorageUnreadable):
            s.commit()
        assert st.DATA_FILE.read_bytes() == prima
    finally:
        crypto_mod.set_key(None)


def test_d4_secondo_commit_non_distrugge_backup():
    s = TodoStore([TodoItem(todo_id=1, title="v1")])
    s.commit()
    v1 = st.DATA_FILE.read_bytes()
    s.add(TodoItem(title="v2"))
    s.commit()
    v2 = st.DATA_FILE.read_bytes()
    bak = st.DATA_FILE.with_suffix(".bak.json")
    bak1 = st.DATA_FILE.with_suffix(".bak.1.json")
    assert bak.read_bytes() == v1
    s.add(TodoItem(title="v3"))
    s.commit()
    assert bak.read_bytes() == v2
    assert bak1.read_bytes() == v1
    assert st.DATA_FILE.read_bytes() != v2


def test_d4_failure_prima_del_replace_non_tocca_nulla(monkeypatch):
    s = TodoStore([TodoItem(todo_id=1, title="v1")])
    s.commit()
    s.add(TodoItem(title="v2"))
    s.commit()
    prima = st.DATA_FILE.read_bytes()
    prima_bak = st.DATA_FILE.with_suffix(".bak.json").read_bytes()

    import pathlib

    _orig_replace = pathlib.Path.replace

    def _boom(self, target):
        if target == st.DATA_FILE:
            raise OSError("disco pieno simulato")
        return _orig_replace(self, target)

    monkeypatch.setattr("pathlib.Path.replace", _boom)
    with pytest.raises(OSError):
        s.add(TodoItem(title="v3"))
        s.commit()
    # replace fallito DOPO la rotazione: primary intatto, versioni
    # conservate (bak=primary corrente, bak.1=precedente). Nessuna perdita.
    assert st.DATA_FILE.read_bytes() == prima
    assert st.DATA_FILE.with_suffix(".bak.json").read_bytes() == prima
    assert st.DATA_FILE.with_suffix(".bak.1.json").read_bytes() == prima_bak


def test_d5_save_normale_plaintext_funziona():
    s = TodoStore([TodoItem(todo_id=1, title="A")])
    s.commit()
    assert _titles(TodoStore.load()) == ["A"]
    st.save_templates({"t": []})
    assert st.load_templates() == st._default_templates()
    st.save_archive([])
    assert st.load_archive() == []
    st.save_pomodoro({})
    assert isinstance(st.load_pomodoro(), dict)


def test_d5_unlock_poi_commit_funziona():
    _seed_envelope_todos()
    assert TodoStore.load().all() == []
    crypto_mod.set_key(encode_password("segreta12"))
    try:
        s = TodoStore.load()
        assert _titles(s) == ["A"]
        s.add(TodoItem(title="B"))
        s.commit()
        assert _titles(TodoStore.load()) == ["A", "B"]
    finally:
        crypto_mod.set_key(None)


def _seed_executions(n=3, actual=2):
    from src.models import TaskExecution

    recs = [
        TaskExecution(
            task_id=i,
            ended_at=f"2026-09-{10 + i:02d}",
            estimate_pomo=1,
            actual_minutes=60 * actual,
        )
        for i in range(1, n + 1)
    ]
    for r in recs:
        st.append_execution(r)
    return recs


def test_b1_executions_sopravvivono_a_enable_change_disable(tmp_files):
    """B1: history leggibile + appendibile dopo ogni rotazione chiave."""
    from tests.conftest import make_app, run

    async def t():
        st._save_todos_plain([TodoItem(todo_id=1, title="A")])
        _seed_executions(3)
        assert len(st.load_executions()) == 3
        app = make_app([TodoItem(todo_id=1, title="A")])
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._sec_enable(["nuova1234", "nuova1234"])
            await pilot.pause()
            assert [e.task_id for e in st.load_executions()] == [1, 2, 3]
            st.append_execution(
                {
                    "task_id": 4,
                    "ended_at": "2026-09-14",
                    "estimate_pomo": 1,
                    "actual_minutes": 120,
                }
            )
            assert len(st.load_executions()) == 4
            app._sec_change(["nuova1234", "altra1234", "altra1234"])
            await pilot.pause()
            assert [e.task_id for e in st.load_executions()] == [1, 2, 3, 4]
            st.append_execution(
                {
                    "task_id": 5,
                    "ended_at": "2026-09-15",
                    "estimate_pomo": 1,
                    "actual_minutes": 120,
                }
            )
            app._sec_disable(["altra1234"])
            await pilot.pause()
            assert not crypto_mod.is_unlocked()
            got = st.load_executions()
            assert [e.task_id for e in got] == [1, 2, 3, 4, 5]
            assert not crypto_mod.is_envelope(
                st.EXECUTIONS_FILE.read_text(encoding="utf-8")
            )

    run(t())


def test_b1_token_preservato_dalla_rotation(tmp_files):
    """B1: il login Outlook sopravvive al cambio password (no logout)."""
    from tests.conftest import make_app, run

    async def t():
        st._save_todos_plain([TodoItem(todo_id=1, title="A")])
        app = make_app([TodoItem(todo_id=1, title="A")])
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._sec_enable(["nuova1234", "nuova1234"])
            await pilot.pause()
            st.save_outlook_token('{"cache": "tok123"}')
            assert st.load_outlook_token() == '{"cache": "tok123"}'
            app._sec_change(["nuova1234", "altra1234", "altra1234"])
            await pilot.pause()
            assert st.load_outlook_token() == '{"cache": "tok123"}'
            app._sec_disable(["altra1234"])
            await pilot.pause()
            assert st.load_outlook_token() == '{"cache": "tok123"}'

    run(t())


def test_b1_calibration_stessa_prima_e_dopo(tmp_files):
    """B1: la calibration sui todos non cambia con la rotation."""
    from src.domain import calibration_factor
    from tests.conftest import make_app, run

    async def t():
        hist = []
        for i in range(5):
            t = TodoItem(todo_id=100 + i, title=f"H{i}")
            t.done = True
            t.stima_pomo = 1
            t.actual_pomo = 2
            hist.append(t)
        st._save_todos_plain([TodoItem(todo_id=1, title="A")] + hist)
        before = calibration_factor(hist)
        assert before == 2.0
        app = make_app([TodoItem(todo_id=1, title="A")] + hist)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._sec_enable(["nuova1234", "nuova1234"])
            await pilot.pause()
            after = calibration_factor(
                [x for x in TodoStore.load().all() if x.state == "completato"]
            )
            assert after == before == 2.0

    run(t())


def test_t1_save_config_fallita_ritorna_false(tmp_files, monkeypatch):
    """T1: errore config mai silenzioso (toast + False, niente successo)."""
    import src.app as app_module
    import src.storage as storage_mod
    from tests.conftest import make_app

    app = make_app([])
    real_save_config = storage_mod.save_config

    def _boom(cfg):
        raise OSError("disco pieno simulato")

    monkeypatch.setattr(app_module, "save_config", _boom)
    assert app._save_config() is False
    # Percorso felice invariato.
    monkeypatch.setattr(app_module, "save_config", real_save_config)
    assert app._save_config() is True


def test_b1_rotation_failure_niente_successo_bugiardo(tmp_files, monkeypatch):
    """P1 review: I/O a meta' rotation -> errore (mai successo),
    backup pre-change creato, file non toccati dal passo fallito."""
    import src.app as app_module
    import src.storage as storage_mod
    from tests.conftest import make_app, run

    async def t():
        st._save_todos_plain([TodoItem(todo_id=1, title="A")])
        st.save_templates({"t": []})
        templates_before = st.TEMPLATE_FILE.read_bytes()
        app = make_app([TodoItem(todo_id=1, title="A")])

        def _boom(*a, **k):
            raise OSError("disco pieno simulato")

        monkeypatch.setattr(storage_mod, "save_templates", _boom)
        monkeypatch.setattr(app_module, "save_templates", _boom)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._sec_enable(["nuova1234", "nuova1234"])
            await pilot.pause()
            # Fallito prima della rewrite: chiave ripristinata, disco intatto.
            assert not crypto_mod.is_unlocked()
            assert st.TEMPLATE_FILE.read_bytes() == templates_before
            assert st.list_snapshots() != []

    run(t())
