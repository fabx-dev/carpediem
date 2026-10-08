"""CLI replan M4: preview read-only, commit solo con --apply.

Un replan non applicato non modifica dati (verifica via hash file);
--apply scrive solo i planned_for; --now invalido = exit 2 senza scrive.
"""

import hashlib

import src.storage as st
from src.cli import _cli_main
from src.lang import T
from src.store import TodoStore
from tests.conftest import make_todo


def _seed(today):
    store = TodoStore(
        [
            make_todo("A", todo_id=1, planned_for=today, stima_pomo=2),
            make_todo("B", todo_id=2, planned_for=today, stima_pomo=2),
            make_todo("C", todo_id=3, stima_pomo=1),
        ]
    )
    store.commit()
    cfg = st.load_config()
    cfg["day_window"] = {
        "date": today,
        "start": "09:00",
        "end": "18:00",
        "events": [],
        "allday": [],
    }
    st.save_config(cfg)


def _hashes():
    out = {}
    for p in (st.DATA_FILE, st.EXECUTIONS_FILE, st.CONFIG_FILE):
        out[str(p)] = hashlib.md5(p.read_bytes()).hexdigest() if p.exists() else None
    return out


def test_preview_readonly(tmp_files, capsys, monkeypatch):
    from datetime import datetime

    today = datetime.now().strftime("%Y-%m-%d")
    _seed(today)
    monkeypatch.setattr("src.cli.datetime", _FakeDateTime(today, 15, 0))
    before = _hashes()
    assert _cli_main(["replan", "--now", "15:00"]) == 0
    assert _hashes() == before  # zero scritture
    out = capsys.readouterr().out
    # F1: scheduled_for_today clippa allo stesso now del replan — il piano
    # corrente e il ricalcolo coincidono (KEPT, non MOVED) + C aggiunto.
    assert T("cli_replan_kept") in out and T("cli_replan_added") in out
    assert T("cli_replan_hint") in out
    assert T("cli_replan_applied").split(":")[0] not in out


def test_apply_committa_solo_planned_for(tmp_files, capsys):
    from datetime import datetime

    today = datetime.now().strftime("%Y-%m-%d")
    _seed(today)
    assert _cli_main(["replan", "--now", "15:00", "--apply"]) == 0
    out = capsys.readouterr().out
    assert T("cli_replan_applied", a=1, d=0) in out
    store = TodoStore.load()
    assert store.by_id(3).planned_for == today
    assert store.by_id(1).planned_for == today


def test_now_invalido_exit_2_senza_scritture(tmp_files, capsys):
    from datetime import datetime

    today = datetime.now().strftime("%Y-%m-%d")
    _seed(today)
    before = _hashes()
    assert _cli_main(["replan", "--now", "xx"]) == 2
    assert _hashes() == before
    assert T("cli_replan_bad") in capsys.readouterr().err


def test_giorno_vuoto_nessuna_modifica(tmp_files, capsys):
    assert _cli_main(["replan", "--now", "09:00"]) == 0
    out = capsys.readouterr().out
    assert T("cli_replan_no_changes") in out


class _FakeDateTime:
    """datetime.now() congelato (solo date/today usati dal CLI replan)."""

    def __init__(self, today, hour, minute):
        import datetime as _dt

        self._today = today
        self._now = _dt.datetime.strptime(
            f"{today} {hour:02d}:{minute:02d}", "%Y-%m-%d %H:%M"
        )
        self._real = _dt.datetime

    def now(self):
        return self._now

    def strptime(self, *a, **k):
        return self._real.strptime(*a, **k)


def test_b2_now_oltre_fine_riga_senza_orario(tmp_files, capsys, monkeypatch):
    """B2: finestra esaurita -> niente slot passati, piano mantenuto com'e'.

    F1+F4: con now oltre la fine non esistono slot futuri (né vecchi né
    nuovi): A/B restano KEPT senza orario (mai resi come cambi di slot),
    il commit resta solo planned_for. Planner invariato (solo rendering)."""
    from datetime import datetime

    today = datetime.now().strftime("%Y-%m-%d")
    _seed(today)
    monkeypatch.setattr("src.cli.datetime", _FakeDateTime(today, 20, 0))
    before = _hashes()
    assert _cli_main(["replan", "--now", "20:00"]) == 0
    assert _hashes() == before  # zero scritture
    out = capsys.readouterr().out
    assert T("cli_replan_kept") in out
    assert "–" not in out  # nessuno slot fantasma, solo titoli + motivi


def test_c4_finestra_corrotta_exit_1_senza_scritture(tmp_files, capsys, monkeypatch):
    """C4: errore reale con finestra odierna -> exit 1, mai degrado."""
    from datetime import datetime

    import src.screens.plan as plan_mod

    today = datetime.now().strftime("%Y-%m-%d")
    _seed(today)
    cfg = st.load_config()
    cfg["day_window"] = {"date": today, "start": "09:00", "end": "18:00", "events": []}
    st.save_config(cfg)
    monkeypatch.setattr(
        plan_mod,
        "day_window_parts",
        lambda *a, **k: (_ for _ in ()).throw(TypeError("finestra rotta")),
    )
    before = _hashes()
    assert _cli_main(["replan", "--now", "15:00"]) == 1
    assert _hashes() == before
    assert (
        "annullato" in capsys.readouterr().err or "aborted" in capsys.readouterr().err
    )


def test_c4_sched_failure_exit_1_senza_apply(tmp_files, capsys, monkeypatch):
    """C4: errore scheduling con finestra valida -> exit 1, apply rifiutato."""
    from datetime import datetime

    import src.screens.plan as plan_mod

    today = datetime.now().strftime("%Y-%m-%d")
    _seed(today)
    monkeypatch.setattr(
        plan_mod,
        "scheduled_for_today",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom planner")),
    )
    before = _hashes()
    assert _cli_main(["replan", "--now", "15:00", "--apply"]) == 1
    assert _hashes() == before


def test_c4_apply_senza_moves_non_committa(tmp_files, capsys):
    """C4: --apply senza mosse non tocca disco ne' .bak."""
    assert _cli_main(["replan", "--now", "09:00", "--apply"]) == 0
    out = capsys.readouterr().out
    assert "Nessuna modifica" in out or "No changes" in out
    assert not st.DATA_FILE.exists()
    assert not st.DATA_FILE.with_suffix(".bak.json").exists()
