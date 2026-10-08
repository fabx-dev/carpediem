"""Equivalenza E1: src/export_ical.py == metodi originali di TodoApp."""

import pathlib

import carpediem.export_ical as ei
from carpediem.models import Priority
from tests.conftest import make_app, make_todo


def _cases():
    return [
        make_todo("Con ora", todo_id=1, due="2026-01-02 09:30", project="work"),
        make_todo("Giorno intero", todo_id=2, due="2026-01-03"),
        make_todo(
            "Speciali ;,\\n",
            todo_id=3,
            due="2026-01-04 10:00",
            tags=["a", "b"],
            notes="riga1\nriga2",
        ),
        make_todo("Alta", todo_id=4, due="2026-01-05", priority=Priority.HIGH),
    ]


def test_escape_equivalente():
    app = make_app([])
    for raw in ["a;b,c\\d\ne", "Progetto: x", "", "09:30"]:
        assert app._ical_escape(raw) == ei.ical_escape(raw)


def test_event_lines_equivalenti():
    app = make_app([])
    for t in _cases():
        parts = (t.due or "").split()
        date_part = parts[0]
        time_part = (
            parts[1]
            if len(parts) >= 2 and len(parts[1]) == 5 and parts[1][2] == ":"
            else ""
        )
        assert app._ical_event_lines(
            t, date_part, time_part, "STAMP"
        ) == ei.ical_event_lines(t, date_part, time_part, "STAMP")


def test_event_lines_contenuto():
    t = make_todo("Con ora", todo_id=1, due="2026-01-02 09:30", project="work")
    lines = ei.ical_event_lines(t, "2026-01-02", "09:30", "STAMP")
    assert lines[0] == "BEGIN:VEVENT" and lines[-1] == "END:VEVENT"
    assert "SUMMARY:Con ora" in lines
    assert "DTSTART:20260102T093000" in lines
    allday = ei.ical_event_lines(
        make_todo("Giorno intero", todo_id=2, due="2026-01-03"),
        "2026-01-03",
        "",
        "STAMP",
    )
    assert "DTSTART;VALUE=DATE:20260103" in allday
    assert "DTEND;VALUE=DATE:20260104" in allday


def test_uid_fallback_deterministico_cross_seed():
    """C1: task senza id -> UID stabile tra processi (sha1, mai hash())."""
    import subprocess
    import sys

    code = (
        "from carpediem.export_ical import ical_event_lines;"
        "from tests.conftest import make_todo;"
        "t = make_todo('X', todo_id=None, due='2026-01-02 09:30');"
        "print([l for l in ical_event_lines(t, '2026-01-02', '09:30', 'S') if l.startswith('UID:')][0])"
    )
    uids = set()
    root = pathlib.Path(__file__).resolve().parent.parent
    for seed in ("0", "1", "42"):
        import os

        env = dict(
            os.environ,
            PYTHONHASHSEED=seed,
            PYTHONPATH=str(root / "src")
            + os.pathsep
            + os.environ.get("PYTHONPATH", ""),
        )
        out = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(root),
        )
        assert out.returncode == 0, out.stderr
        uids.add(out.stdout.strip())
    assert len(uids) == 1, uids
    assert uids.pop().startswith("UID:carpediem-noid-")


def test_uid_con_id_invariato():
    """C1: ramo id = identita' canonica, intatto."""
    t = make_todo("X", todo_id=7, due="2026-01-02 09:30")
    lines = ei.ical_event_lines(t, "2026-01-02", "09:30", "S")
    assert "UID:carpediem-7@carpediem.local" in lines


def test_dtend_da_stima_e_default_30m():
    """C1.5: timed ha DTEND = start + stima (30m se assente)."""
    t = make_todo("X", todo_id=1, due="2026-01-02 09:30", stima_pomo=2)
    lines = ei.ical_event_lines(t, "2026-01-02", "09:30", "S")
    assert "DTSTART:20260102T093000" in lines
    assert "DTEND:20260102T103000" in lines
    t0 = make_todo("Y", todo_id=2, due="2026-01-02 09:30")
    lines0 = ei.ical_event_lines(t0, "2026-01-02", "09:30", "S")
    assert "DTEND:20260102T100000" in lines0


def test_fold_75_ottetti_e_unfold():
    """C1.6: righe lunghe piegate RFC 5545, unfold = originale."""
    t = make_todo("Z", todo_id=3, due="2026-01-03", notes="n" * 200)
    lines = ei.ical_event_lines(t, "2026-01-03", "", "S")
    assert all(len(line.encode("utf-8")) <= 75 for line in lines)
    unfolded = []
    for line in lines:
        if line.startswith(" ") and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    assert any("n" * 200 in u for u in unfolded)
    # Mai spezzare codepoint: titolo con emoji lunga.
    te = make_todo("E" + "🎉" * 40, todo_id=4, due="2026-01-04")
    le = ei.ical_event_lines(te, "2026-01-04", "", "S")
    assert all(len(line.encode("utf-8")) <= 75 for line in le)
    ue = []
    for line in le:
        if line.startswith(" ") and ue:
            ue[-1] += line[1:]
        else:
            ue.append(line)
    assert any("🎉" * 40 in u for u in ue)


def test_cr_normalizzato_in_escape():
    """C1.7: \\r\\n e \\r isolati non rompono le righe .ics."""
    assert ei.ical_escape("a\r\nb\rc") == "a\\nb\\nc"
