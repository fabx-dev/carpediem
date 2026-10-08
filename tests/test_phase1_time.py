"""Phase 1 Step 3 — T4/T5: explicit time (docs/planner-phase1-plan.md §6).

Precedenza esplicita (today > now > fallback compat allowlisted), date come
input, audit dei caller di produzione (tutti espliciti: la migrazione Step 3
e' no-op sui caller), determinismo sotto clock congelato/variato.
"""

import random
import sys
from datetime import date, datetime

import carpediem.planner.service as service_mod
from carpediem.planner import Planner
from carpediem.planner.models import TimeWindow
from carpediem.planner.replan import replan
from tests.conftest import make_todo

# Vedi test_phase1_characterization.py: import-as lega la funzione, non il modulo.
replan_mod = sys.modules["carpediem.planner.replan"]

TODAY = "2026-09-10"
DAY = (2026, 9, 10)
FROZEN_NOW = datetime(2026, 9, 10, 15, 30)


def _win(h1, m1, h2, m2):
    return TimeWindow(datetime(*DAY, h1, m1), datetime(*DAY, h2, m2))


def _freeze_clock(monkeypatch, at=FROZEN_NOW):
    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return at

    monkeypatch.setattr(service_mod, "datetime", _Frozen)
    monkeypatch.setattr(replan_mod, "datetime", _Frozen)


# --- T4: precedenza e tipi ----------------------------------------------------


def test_t4_parse_day_accetta_date_e_datetime():
    from carpediem.planner import scoring

    assert scoring.parse_day(TODAY) == date(*DAY)
    assert scoring.parse_day(date(*DAY)) == date(*DAY)
    assert scoring.parse_day(datetime(*DAY, 15, 30)) == date(*DAY)
    assert scoring.parse_day("xx") is None
    assert scoring.parse_day("") is None
    assert scoring.parse_day(None) is None


def test_t4_today_vince_su_now_vince_su_fallback(monkeypatch):
    _freeze_clock(monkeypatch)
    todos = [make_todo("A", todo_id=1)]
    assert str(Planner(todos).propose().day) == TODAY  # fallback compat
    assert str(Planner(todos, now=date(2026, 9, 11)).propose().day) == "2026-09-11"
    assert (
        str(Planner(todos, today="2026-09-12", now=date(2026, 9, 11)).propose().day)
        == "2026-09-12"
    )
    # now datetime: conta solo la parte data
    assert (
        str(Planner(todos, now=datetime(2026, 9, 11, 23, 59)).propose().day)
        == "2026-09-11"
    )
    # garbage esplicito -> catena verso il fallback, mai eccezioni
    assert str(Planner(todos, today="xx").propose().day) == TODAY


def test_t4_replan_now_date_e_mezzanotte():
    todos = [make_todo("A", todo_id=1, planned_for=TODAY)]
    avail = [_win(9, 0, 18, 0)]
    p = replan(todos, TODAY, 6.0, avail, (), date(*DAY))
    assert p.now == datetime(*DAY, 0, 0)


def test_t4_replan_fallback_uguale_a_esplicito(monkeypatch):
    _freeze_clock(monkeypatch)
    todos = [make_todo("A", todo_id=1, planned_for=TODAY)]
    avail = [_win(9, 0, 18, 0)]
    assert replan(todos, TODAY, 6.0, avail, (), None) == replan(
        todos, TODAY, 6.0, avail, (), FROZEN_NOW
    )


# --- T4 audit: caller di produzione sempre espliciti --------------------------
#
# Audit 2026-09-30 (verificato a mano, fissato qui): ogni Planner( di
# produzione passa today= per keyword; ogni replan( passa now (posizionale
# 6. argomento o keyword). plan_day/test/script possono omettere (compat).


def _calls_from(path, name):
    import pathlib
    import re

    src = pathlib.Path(path).read_text(encoding="utf-8")
    # Solo chiamate vere: mai sottostringhe (es. apply_replan per replan).
    out = []
    for m in re.finditer(r"(?<![\w.])" + name + r"\(", src):
        i = m.end() - 1
        depth, j = 0, i
        for k in range(j, len(src)):
            if src[k] == "(":
                depth += 1
            elif src[k] == ")":
                depth -= 1
                if depth == 0:
                    out.append(src[j : k + 1])
                    break
    return out


def _top_args(call):
    inner = call[call.index("(") + 1 : -1]
    parts, depth, cur = [], 0, ""
    for ch in inner:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return parts


def test_t4_audit_caller_produzione_espliciti():
    for path in (
        "src/carpediem/screens/plan.py",
        "src/carpediem/screens/views.py",
        "src/carpediem/app.py",
    ):
        for call in _calls_from(path, "Planner"):
            assert "today=" in call, f"{path}: {call[:60]}"
    for path in ("src/carpediem/screens/plan.py", "src/carpediem/cli.py"):
        calls = _calls_from(path, "replan")
        assert calls, f"{path}: nessun replan( trovato"
        for call in calls:
            args = _top_args(call)
            assert "now=" in call or len(args) >= 6, f"{path}: {call[:80]}"


# --- T5: determinismo ----------------------------------------------------------


def test_t5_shuffle_stesso_output():
    rng = random.Random(42)
    todos = [
        make_todo(f"T{i:03d}", todo_id=i, due=f"2026-09-{(i % 28) + 1:02d}")
        for i in range(1, 201)
    ]
    expected = Planner(todos, today=TODAY, hours=6.0).propose().to_legacy()
    for _ in range(5):
        shuffled = list(todos)
        rng.shuffle(shuffled)
        assert (
            Planner(shuffled, today=TODAY, hours=6.0).propose().to_legacy() == expected
        )


def test_t5_scheduler_indipendente_dal_wall_clock(monkeypatch):
    todos = [
        make_todo("A", todo_id=1, stima_pomo=2),
        make_todo("B", todo_id=2, stima_pomo=2),
    ]
    plan = Planner(todos, today=TODAY, hours=6.0).propose()
    avail = [_win(9, 0, 18, 0)]
    first = Planner.schedule(plan, avail, ())
    for day, hour in ((11, 8), (12, 23), (9, 0)):
        _freeze_clock(monkeypatch, datetime(2026, 9, day, hour, 0))
        assert Planner.schedule(plan, avail, ()) == first


def test_t5_replan_deterministico_con_now_esplicito():
    todos = [
        make_todo("A", todo_id=1, planned_for=TODAY, stima_pomo=2),
        make_todo("B", todo_id=2, stima_pomo=2),
    ]
    avail = [_win(9, 0, 18, 0)]
    now = datetime(*DAY, 15, 30)
    assert replan(todos, TODAY, 6.0, avail, (), now) == replan(
        todos, TODAY, 6.0, avail, (), now
    )
