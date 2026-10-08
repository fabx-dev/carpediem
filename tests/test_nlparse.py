"""Test parser NL deterministico it/en (funzione pura, nessun file)."""

from datetime import datetime, timedelta

from carpediem.models import Priority, Recurrence
from carpediem.nlparse import parse


def _today(offset: int = 0) -> str:
    return (datetime.now().date() + timedelta(days=offset)).strftime("%Y-%m-%d")


def _next_wd(idx: int, weeks: int = 0) -> str:
    today = datetime.now().date()
    delta = (idx - today.weekday()) % 7
    if delta == 0:
        delta = 7
    return (today + timedelta(days=delta + 7 * weeks)).strftime("%Y-%m-%d")


def _exp(**kw):
    base = {
        "title": "",
        "priority": Priority.MEDIUM,
        "due": "",
        "notes": "",
        "recurrence": Recurrence.NONE,
        "tags": [],
        "project": "",
        "stima_pomo": 0,
    }
    base.update(kw)
    return base


def _slash_day_month(day: int, month: int) -> str:
    today = datetime.now().date()
    try:
        cand = today.replace(month=month, day=day)
    except ValueError:
        return ""
    if cand < today:
        cand = cand.replace(year=cand.year + 1)
    return cand.strftime("%Y-%m-%d")


CASES_IT = [
    ("compra latte", _exp(title="compra latte")),
    ("", _exp()),
    ("   ", _exp()),
    ("compra latte domani", _exp(title="compra latte", due=_today(1))),
    ("riunione domani alle 17:00", _exp(title="riunione", due=_today(1) + " 17:00")),
    ("dentista oggi ore 9:00", _exp(title="dentista", due=_today() + " 09:00")),
    ("call oggi", _exp(title="call", due=_today())),
    ("x dopodomani", _exp(title="x", due=_today(2))),
    ("x tra 3 giorni", _exp(title="x", due=_today(3))),
    ("x tra 1 giorno", _exp(title="x", due=_today(1))),
    ("palestra lunedì", _exp(title="palestra", due=_next_wd(0))),
    ("yoga lunedi", _exp(title="yoga", due=_next_wd(0))),
    ("corsa ven", _exp(title="corsa", due=_next_wd(4))),
    ("pranzo Domenica", _exp(title="pranzo", due=_next_wd(6))),
    ("DENTISTA Domani Alle 17:00", _exp(title="DENTISTA", due=_today(1) + " 17:00")),
    ("palestra lunedì prossimo", _exp(title="palestra", due=_next_wd(0, 1))),
    (
        "yoga ogni lunedì",
        _exp(title="yoga", due=_next_wd(0), recurrence=Recurrence.WEEKLY),
    ),
    ("backup ogni giorno", _exp(title="backup", recurrence=Recurrence.DAILY)),
    ("report ogni settimana", _exp(title="report", recurrence=Recurrence.WEEKLY)),
    ("bollette ogni mese", _exp(title="bollette", recurrence=Recurrence.MONTHLY)),
    (
        "assicurazione ogni anno",
        _exp(title="assicurazione", recurrence=Recurrence.YEARLY),
    ),
    ("pulizia giornaliero", _exp(title="pulizia", recurrence=Recurrence.DAILY)),
    ("sync settimanale", _exp(title="sync", recurrence=Recurrence.WEEKLY)),
    (
        "sveglia ogni giorno alle 9:00",
        _exp(title="sveglia", due=_today() + " 09:00", recurrence=Recurrence.DAILY),
    ),
    ("compra latte #casa", _exp(title="compra latte", tags=["casa"])),
    ("x #a #b #a", _exp(title="x", tags=["a", "b"])),
    ("x #Casa", _exp(title="x", tags=["casa"])),
    ("festa #amici!", _exp(title="festa !", tags=["amici"])),
    ("task *lavoro", _exp(title="task", project="lavoro")),
    ("task *Lavoro", _exp(title="task", project="lavoro")),
    ("a *x b *y", _exp(title="a b", project="y")),
    ("urgente !alta", _exp(title="urgente", priority=Priority.HIGH)),
    ("x !1", _exp(title="x", priority=Priority.HIGH)),
    ("x !2", _exp(title="x", priority=Priority.MEDIUM)),
    ("x !3", _exp(title="x", priority=Priority.LOW)),
    ("x !media", _exp(title="x", priority=Priority.MEDIUM)),
    ("x !bassa", _exp(title="x", priority=Priority.LOW)),
    ("x !boh", _exp(title="x !boh")),
    ("a !bassa b !alta", _exp(title="a b", priority=Priority.HIGH)),
    ("film ~2", _exp(title="film", stima_pomo=2)),
    ("serie ~0", _exp(title="serie", stima_pomo=0)),
    ("call 17:00", _exp(title="call", due=_today() + " 17:00")),
    ("call 9:05", _exp(title="call", due=_today() + " 09:05")),
    ("call 99:99", _exp(title="call 99:99")),
    ("call 25:00", _exp(title="call 25:00")),
    ("report 2026-12-01 09:30", _exp(title="report", due="2026-12-01 09:30")),
    ("scadenza 15/09/2026", _exp(title="scadenza", due="2026-09-15")),
    ("festa 05/03", _exp(title="festa", due=_slash_day_month(5, 3))),
    ("natale 25/12", _exp(title="natale", due=_slash_day_month(25, 12))),
    ("x 29/02/2026", _exp(title="x 29/02/2026")),
    ("ciao! come va", _exp(title="ciao! come va")),
    ("nota: comprare pane", _exp(title="nota: comprare pane")),
    ("task *", _exp(title="task *")),
    ("task #", _exp(title="task #")),
    ("  spazi   doppi   domani  ", _exp(title="spazi doppi", due=_today(1))),
    ("latte, domani", _exp(title="latte", due=_today(1))),
    ("a domani b dopodomani", _exp(title="a b", due=_today(2))),
    (
        "report *lavoro #ufficio !alta ~3 domani alle 18:00",
        _exp(
            title="report",
            project="lavoro",
            tags=["ufficio"],
            priority=Priority.HIGH,
            stima_pomo=3,
            due=_today(1) + " 18:00",
        ),
    ),
]

CASES_EN = [
    ("buy milk", _exp(title="buy milk")),
    ("buy milk tomorrow", _exp(title="buy milk", due=_today(1))),
    ("meeting tomorrow at 17:00", _exp(title="meeting", due=_today(1) + " 17:00")),
    ("dentist today at 09:00", _exp(title="dentist", due=_today() + " 09:00")),
    ("call today", _exp(title="call", due=_today())),
    ("x day after tomorrow", _exp(title="x", due=_today(2))),
    ("x in 3 days", _exp(title="x", due=_today(3))),
    ("x in 1 day", _exp(title="x", due=_today(1))),
    ("gym monday", _exp(title="gym", due=_next_wd(0))),
    ("run fri", _exp(title="run", due=_next_wd(4))),
    ("lunch Sunday", _exp(title="lunch", due=_next_wd(6))),
    ("GYM Tomorrow At 17:00", _exp(title="GYM", due=_today(1) + " 17:00")),
    ("gym next monday", _exp(title="gym", due=_next_wd(0, 1))),
    (
        "yoga every monday",
        _exp(title="yoga", due=_next_wd(0), recurrence=Recurrence.WEEKLY),
    ),
    ("backup every day", _exp(title="backup", recurrence=Recurrence.DAILY)),
    ("report every week", _exp(title="report", recurrence=Recurrence.WEEKLY)),
    ("bills every month", _exp(title="bills", recurrence=Recurrence.MONTHLY)),
    ("insurance every year", _exp(title="insurance", recurrence=Recurrence.YEARLY)),
    ("cleanup daily", _exp(title="cleanup", recurrence=Recurrence.DAILY)),
    ("sync weekly", _exp(title="sync", recurrence=Recurrence.WEEKLY)),
    ("review monthly", _exp(title="review", recurrence=Recurrence.MONTHLY)),
    ("party yearly", _exp(title="party", recurrence=Recurrence.YEARLY)),
    (
        "wake every day at 09:00",
        _exp(title="wake", due=_today() + " 09:00", recurrence=Recurrence.DAILY),
    ),
    ("buy milk #home", _exp(title="buy milk", tags=["home"])),
    ("x #a #b #a", _exp(title="x", tags=["a", "b"])),
    ("task *work", _exp(title="task", project="work")),
    ("a *x b *y", _exp(title="a b", project="y")),
    ("urgent !high", _exp(title="urgent", priority=Priority.HIGH)),
    ("x !1", _exp(title="x", priority=Priority.HIGH)),
    ("x !2", _exp(title="x", priority=Priority.MEDIUM)),
    ("x !3", _exp(title="x", priority=Priority.LOW)),
    ("x !medium", _exp(title="x", priority=Priority.MEDIUM)),
    ("x !low", _exp(title="x", priority=Priority.LOW)),
    ("x !whatever", _exp(title="x !whatever")),
    ("a !low b !high", _exp(title="a b", priority=Priority.HIGH)),
    ("movie ~2", _exp(title="movie", stima_pomo=2)),
    ("call 17:00", _exp(title="call", due=_today() + " 17:00")),
    ("call 25:00", _exp(title="call 25:00")),
    ("call at 5pm", _exp(title="call at 5pm")),
    ("report 2026-12-01 09:30", _exp(title="report", due="2026-12-01 09:30")),
    ("party 25/12", _exp(title="party", due=_slash_day_month(25, 12))),
    ("deadline 03/05/2026", _exp(title="deadline", due="2026-05-03")),
    ("hello! how are you", _exp(title="hello! how are you")),
    ("task *", _exp(title="task *")),
    ("  extra   spaces   tomorrow  ", _exp(title="extra spaces", due=_today(1))),
    ("milk, tomorrow", _exp(title="milk", due=_today(1))),
    ("a tomorrow b day after tomorrow", _exp(title="a b", due=_today(2))),
    ("watch the sun sunday", _exp(title="watch the", due=_next_wd(6))),
    (
        "report *work #office !high ~3 tomorrow at 18:00",
        _exp(
            title="report",
            project="work",
            tags=["office"],
            priority=Priority.HIGH,
            stima_pomo=3,
            due=_today(1) + " 18:00",
        ),
    ),
]


def test_casi_italiano():
    assert len(CASES_IT) >= 40
    for text, expected in CASES_IT:
        assert parse(text, "it") == expected, text


def test_casi_inglese():
    assert len(CASES_EN) >= 40
    for text, expected in CASES_EN:
        assert parse(text, "en") == expected, text


def test_default_e_lingua_sconosciuta():
    assert parse("compra latte domani") == parse("compra latte domani", "it")
    assert parse("x domani", "xx") == parse("x domani", "it")
    assert parse("x domani", "") == parse("x domani", "it")
    assert parse("buy milk tomorrow", "en")["due"] == _today(1)
    # le parole chiave non sono cross-lingua
    assert parse("buy milk tomorrow", "it")["title"] == "buy milk tomorrow"
    assert parse("compra latte domani", "en")["title"] == "compra latte domani"


def test_enum_e_due_valido():
    res = parse("x domani alle 17:00 *p #t !alta ~2 ogni giorno", "it")
    assert isinstance(res["priority"], Priority)
    assert isinstance(res["recurrence"], Recurrence)
    assert res["due"] == _today(1) + " 17:00"
    assert res["project"] == "p"
    assert res["tags"] == ["t"]
    assert res["stima_pomo"] == 2
    assert res["notes"] == ""


def test_note_doppio_slash(tmp_files):
    res = parse("call domani // portare documenti #veri", "it")
    assert res["title"] == "call"
    assert res["due"] == _today(1)
    assert res["notes"] == "portare documenti #veri"
    assert res["tags"] == []
    res = parse("// solo nota", "it")
    assert res["title"] == ""
    assert res["notes"] == "solo nota"
    res = parse("meeting tomorrow // bring slides", "en")
    assert res["title"] == "meeting"
    assert res["due"] == _today(1)
    assert res["notes"] == "bring slides"


def test_doppio_slash_non_in_url():
    res = parse("leggi https://esempio.it/x domani", "it")
    assert res["notes"] == ""
    assert res["title"] == "leggi https://esempio.it/x"
    assert res["due"] == _today(1)
    res = parse("x//y domani", "it")
    assert res["title"] == "x//y"
    assert res["due"] == _today(1)


def test_parse_with_found():
    from carpediem.nlparse import parse_with_found

    res, found = parse_with_found("call domani *p", "it")
    assert found == {"title", "due", "project"}
    assert res["title"] == "call"
    res, found = parse_with_found("Solo titolo", "it")
    assert found == {"title"}
    res, found = parse_with_found("x #a ~2 // nota", "it")
    assert found == {"title", "tags", "stima_pomo", "notes"}
    assert res["notes"] == "nota"
