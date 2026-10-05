"""Integrazione Outlook B2: auth/fetch con doppi iniettati (mai rete, mai msal).

Copre: silent ok/ko, binding account, device flow (uri validata), fetch
calendarView, token file (0600, roundtrip, delete, fuori dai backup),
validazione config outlook + whitelist, guardrail import nelle screen.
"""

import os
import pathlib

import pytest

import src.storage as storage
from src.integrations.outlook_auth import OutlookClient, OutlookError, disconnect

DAY = "2026-09-23"
CFG = {
    "client_id": "00000000-0000-4000-8000-000000000000",
    "tenant": "11111111-1111-4111-8111-111111111111",
    "account": "m.rossi@azienda.it",
    "tz": "Europe/Rome",
}


class FakeCache:
    def __init__(self, blob='{"AccessToken": {}}'):
        self.blob = blob

    def serialize(self):
        return self.blob

    def deserialize(self, s):
        self.blob = s


class FakeClient:
    def __init__(self, accounts=(), silent=None, auth_flow=None, auth_token=None):
        self.accounts = list(accounts)
        self.silent = silent
        self.auth_flow = auth_flow
        if self.auth_flow is None:
            self.auth_flow = {
                "auth_uri": "https://login.microsoftonline.com/t/authorize"
            }
        self.auth_token = auth_token
        self.scopes_seen = None
        self.redirect_seen = None

    def get_accounts(self):
        return list(self.accounts)

    def acquire_token_silent(self, scopes, account):
        self.scopes_seen = list(scopes)
        return self.silent

    def initiate_auth_code_flow(self, scopes, redirect_uri=None, login_hint=None):
        self.scopes_seen = list(scopes)
        self.redirect_seen = redirect_uri
        self.login_hint_seen = login_hint
        return dict(self.auth_flow or {})

    def acquire_token_by_authorization_code(self, code, scopes=None, redirect_uri=None):
        assert code == "AUTHCODE"
        return self.auth_token


class FakeListener:
    def __init__(self, code="AUTHCODE", closed=None):
        self.redirect_uri = "http://127.0.0.1:9/callback"
        self._code = code
        self.closed = closed if closed is not None else []

    def wait(self, timeout=None):
        if isinstance(self._code, Exception):
            raise self._code
        return self._code

    def close(self):
        self.closed.append(True)

    def abort(self):
        self.closed.append("aborted")
        self.close()


def _acc(username):
    return {"username": username}


def _token(username="m.rossi@azienda.it"):
    return {
        "access_token": "AT",
        "id_token_claims": {"preferred_username": username},
    }


def _client(**kw):
    return OutlookClient(dict(CFG), client=FakeClient(**kw), cache=FakeCache())


def test_silent_ok_e_binding(tmp_files):
    c = _client(accounts=[_acc("m.rossi@azienda.it")], silent=_token())
    token, adopted = c.token_silent()
    assert token == "AT" and adopted == "m.rossi@azienda.it"
    assert c._client.scopes_seen == ["Calendars.Read"]


def test_silent_senza_account_none(tmp_files):
    assert _client(accounts=[]).token_silent() == (None, "")


def test_silent_account_sbagliato_mismatch(tmp_files):
    c = _client(
        accounts=[_acc("collega@azienda.it")], silent=_token("collega@azienda.it")
    )
    # L'account in cache non matcha quello in config: niente token.
    assert c.token_silent() == (None, "")
    # E se il token dichiara un altro utente: fail-closed esplicito.
    c2 = _client(accounts=[_acc("m.rossi@azienda.it")], silent=_token("intruso@x.it"))
    with pytest.raises(OutlookError) as ei:
        c2.token_silent()
    assert ei.value.code == "account_mismatch"


def test_authcode_start_apre_browser_e_redirect_loopback(tmp_files):
    opened = []
    c = OutlookClient(
        dict(CFG),
        client=FakeClient(
            auth_flow={"auth_uri": "https://login.microsoftonline.com/x/authorize?a=1"}
        ),
        cache=FakeCache(),
        listener_factory=lambda: FakeListener(),
        opener=lambda url: opened.append(url) or True,
    )
    started = c.authcode_start()
    assert started["browser_opened"] is True
    assert opened == ["https://login.microsoftonline.com/x/authorize?a=1"]
    assert started["uri"].startswith("https://")
    assert c._client.redirect_seen == "http://127.0.0.1:9/callback"
    assert c._client.login_hint_seen == "m.rossi@azienda.it"


def test_authcode_login_hint_vuoto_none(tmp_files):
    cfg = dict(CFG, account="")
    c = OutlookClient(
        cfg,
        client=FakeClient(),
        cache=FakeCache(),
        listener_factory=lambda: FakeListener(),
        opener=lambda url: True,
    )
    c.authcode_start()
    assert c._client.login_hint_seen is None


def test_authcode_start_browser_ko_url_manuale(tmp_files):
    c = OutlookClient(
        dict(CFG),
        client=FakeClient(
            auth_flow={"auth_uri": "https://login.microsoftonline.com/x"}
        ),
        cache=FakeCache(),
        listener_factory=lambda: FakeListener(),
        opener=lambda url: False,
    )
    started = c.authcode_start()
    assert started["browser_opened"] is False
    assert started["uri"].startswith("https://")


def test_authcode_start_uri_sospetta_rifiutata(tmp_files):
    c = OutlookClient(
        dict(CFG),
        client=FakeClient(auth_flow={"auth_uri": "http://evil.example/login"}),
        cache=FakeCache(),
        listener_factory=lambda: FakeListener(),
        opener=lambda url: True,
    )
    with pytest.raises(OutlookError) as ei:
        c.authcode_start()
    assert ei.value.code == "bad_auth_uri"


def test_authcode_finish_salva_cache_0600(tmp_files):
    c = OutlookClient(
        dict(CFG),
        client=FakeClient(auth_token=_token()),
        cache=FakeCache(),
        listener_factory=lambda: FakeListener(),
        opener=lambda url: True,
    )
    handle = c.authcode_start()["handle"]
    token, user = c.authcode_finish(handle)
    assert token == "AT" and user == "m.rossi@azienda.it"
    assert storage.load_outlook_token() == '{"AccessToken": {}}'
    # Mode-bit POSIX: su Windows gli ACL non li esprimono (best-effort).
    if os.name == "posix":
        mode = oct(os.stat(storage.OUTLOOK_TOKEN_FILE).st_mode & 0o777)
        assert mode == "0o600"


def test_authcode_denied_e_mismatch(tmp_files):
    from src.integrations.outlook_auth import OutlookError as OE

    c = OutlookClient(
        dict(CFG),
        client=FakeClient(auth_token=_token()),
        cache=FakeCache(),
        listener_factory=lambda: FakeListener(
            code=OE("authcode_denied", "access_denied")
        ),
        opener=lambda url: True,
    )
    handle = c.authcode_start()["handle"]
    with pytest.raises(OutlookError) as ei:
        c.authcode_finish(handle)
    assert ei.value.code == "authcode_denied"
    c2 = OutlookClient(
        dict(CFG),
        client=FakeClient(auth_token=_token("intruso@x.it")),
        cache=FakeCache(),
        listener_factory=lambda: FakeListener(),
        opener=lambda url: True,
    )
    with pytest.raises(OutlookError) as ei2:
        c2.authcode_finish(c2.authcode_start()["handle"])
    assert ei2.value.code == "account_mismatch"


def test_loopback_reale_solo_locale(tmp_files):
    import urllib.request

    from src.integrations.outlook_auth import LoopbackListener

    lst = LoopbackListener()
    assert lst.redirect_uri.startswith("http://127.0.0.1:")
    url = lst.redirect_uri + "?code=AUTHCODE"
    with urllib.request.urlopen(url, timeout=5) as resp:
        assert resp.status == 200
    assert lst.wait(timeout=5) == "AUTHCODE"


def test_loopback_timeout_chiude(tmp_files):
    from src.integrations.outlook_auth import LoopbackListener

    lst = LoopbackListener()
    with pytest.raises(OutlookError) as ei:
        lst.wait(timeout=0.1)
    assert ei.value.code == "loopback_timeout"


def test_cancel_authcode_chiude_listener(tmp_files):
    closed: list = []
    c = _client()
    handle = {"flow": {}, "listener": FakeListener(closed=closed)}
    c.cancel_authcode(handle)
    assert closed == ["aborted", True]  # abort sveglia il wait, poi chiude
    c.cancel_authcode(None)
    c.cancel_authcode({})


def test_loopback_solo_127_0_0_1(tmp_files):
    import re

    from src.integrations import outlook_auth as auth_mod

    assert auth_mod.LOOPBACK_HOST == "127.0.0.1"
    src = pathlib.Path("src/integrations/outlook_auth.py").read_text(encoding="utf-8")
    # Niente bind su wildcard (i commenti possono nominarlo, il codice no).
    assert not re.search(r"""\(["']0\.0\.0\.0["']""", src)


def test_fetch_day_parsa_eventi(tmp_files):
    payload = {
        "value": [
            {
                "subject": "Daily",
                "start": {
                    "dateTime": f"{DAY}T09:00:00.0000000",
                    "timeZone": "W. Europe Standard Time",
                },
                "end": {
                    "dateTime": f"{DAY}T09:15:00.0000000",
                    "timeZone": "W. Europe Standard Time",
                },
                "showAs": "busy",
            }
        ]
    }
    seen = {}

    def fake_http(url, token, tz):
        seen["url"] = url
        seen["token"] = token
        seen["tz"] = tz
        return payload

    c = OutlookClient(
        dict(CFG), client=FakeClient(), cache=FakeCache(), http_get=fake_http
    )
    events, allday, skipped = c.fetch_day("AT", DAY)
    assert [e.title for e in events] == ["Daily"]
    assert allday == [] and skipped == []
    assert "calendarview" in seen["url"] and seen["token"] == "AT"
    assert seen["tz"] == "Europe/Rome"
    # Il token non finisce mai nell'URL.
    assert "AT" not in seen["url"].replace("Bearer", "")


def test_fetch_day_payload_scartato(tmp_files):
    c = OutlookClient(
        dict(CFG),
        client=FakeClient(),
        cache=FakeCache(),
        http_get=lambda u, t, z: {"niente": 1},
    )
    with pytest.raises(OutlookError) as ei:
        c.fetch_day("AT", DAY)
    assert ei.value.code == "bad_payload"


def test_http_error_mapping(tmp_files, monkeypatch):
    import urllib.request

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(OutlookError) as ei:
        OutlookClient._http_get_default(
            "https://graph.microsoft.com/x", "AT", "Europe/Rome"
        )
    assert ei.value.code == "admin_consent"


def test_disconnect_cancella_token(tmp_files):
    storage.save_outlook_token('{"a": 1}')
    assert storage.OUTLOOK_TOKEN_FILE.exists()
    disconnect()
    assert not storage.OUTLOOK_TOKEN_FILE.exists()
    assert storage.load_outlook_token() is None


def test_token_fuori_dai_backup(tmp_files):
    names = [n for n, _p in storage._backup_sources()]
    assert "outlook" not in " ".join(names)
    assert all("outlook" not in str(p).lower() for _n, p in storage._backup_sources())


def test_config_outlook_validazione(tmp_files):
    v = storage._validate_outlook(dict(CFG))
    assert v == dict(CFG)
    for bad in (
        None,
        {},
        {"client_id": "", "tenant": "t"},
        {"client_id": "x", "tenant": "common"},
        {"client_id": "x", "tenant": "consumers"},
        {"client_id": "x", "tenant": "t", "account": "non-email"},
        {"client_id": "x", "tenant": "t", "tz": "Atlantis"},
    ):
        if isinstance(bad, dict) and bad.get("tz") == "Atlantis":
            assert storage._validate_outlook(bad)["tz"] == "Europe/Rome"
        else:
            assert storage._validate_outlook(bad) is None, bad


def test_config_outlook_roundtrip_whitelist(tmp_files):
    cfg = storage.load_config()
    cfg["outlook"] = dict(CFG)
    storage.save_config(cfg)
    assert storage.load_config()["outlook"] == dict(CFG)
    # Tutte le chiavi di default sopravvivono al roundtrip.
    for key in storage.DEFAULT_CONFIG:
        assert key in storage.load_config()


def test_screen_mai_import_outlook_auth():
    import re

    pat = re.compile(r"^\s*(import|from)\s+[\w.]*outlook_auth", re.M)
    for path in sorted(pathlib.Path("src/screens").glob("*.py")):
        src = path.read_text(encoding="utf-8")
        assert not pat.search(src), f"{path}: le screen non toccano rete/auth"


def _page(items, nxt=None):
    p = {"value": items}
    if nxt is not None:
        p["@odata.nextLink"] = nxt
    return p


ROM = "W. Europe Standard Time"


def _item(i):
    h = 9 + (i // 2)
    m = "00" if i % 2 == 0 else "30"
    return {
        "subject": f"E{i:02d}",
        "start": {"dateTime": f"{DAY}T{h:02d}:{m}:00", "timeZone": ROM},
        "end": {
            "dateTime": f"{DAY}T{h:02d}:{30 if m == '00' else '45'}:00",
            "timeZone": ROM,
        },
        "showAs": "busy",
    }


def test_fetch_day_segue_nextlink_fino_a_esaurimento(tmp_files):
    p1 = _page([_item(i) for i in range(50)], "https://graph/x?$skip=50")
    p2 = _page([_item(50 + i) for i in range(20)])
    calls = []

    def fake_http(url, token, tz):
        calls.append(url)
        return p2 if "$skip=50" in url else p1

    c = OutlookClient(
        dict(CFG), client=FakeClient(), cache=FakeCache(), http_get=fake_http
    )
    events, allday, skipped = c.fetch_day("AT", DAY)
    assert [u for u in calls if "$skip=50" in u] != []
    assert len(events) == 30  # cap dopo il sort: primi cronologici
    assert [e.title for e in events] == [f"E{i:02d}" for i in range(30)]
    assert len(skipped) == 40  # eccedenza contata, mai silenziosa


def test_fetch_day_nextlink_self_loop_si_ferma(tmp_files):
    # Server patologico: ogni pagina punta a se stessa. Un solo fetch,
    # nessun duplicato, nessun loop.
    calls = []

    def fake_http(url, token, tz):
        calls.append(url)
        return {"value": [_item(0)], "@odata.nextLink": url}

    c = OutlookClient(
        dict(CFG), client=FakeClient(), cache=FakeCache(), http_get=fake_http
    )
    events, _, _ = c.fetch_day("AT", DAY)
    assert len(calls) == 1
    assert [e.title for e in events] == ["E00"]


def test_abort_sveglia_wait_reale(tmp_files):
    """C5: Esc durante wait() non lascia 180s di attesa orfana."""
    import threading
    import time

    from src.integrations.outlook_auth import LoopbackListener

    lst = LoopbackListener()
    outcome = {}

    def _wait():
        try:
            lst.wait(timeout=180)
            outcome["ok"] = True
        except Exception as exc:  # noqa: BLE001 - il codice errore e' l'assert
            outcome["err"] = getattr(exc, "code", type(exc).__name__)

    th = threading.Thread(target=_wait, daemon=True)
    th.start()
    time.sleep(0.3)
    t0 = time.monotonic()
    lst.abort()
    th.join(timeout=10)
    dt = time.monotonic() - t0
    assert not th.is_alive()
    assert dt < 5, dt
    assert outcome.get("err") == "authcode_denied"


def test_http_401_429_timeout_mappati(tmp_files, monkeypatch):
    """C5/G11: token scaduto, rate-limit e rete lenta hanno codici stabili."""
    import urllib.request

    cases = [
        (
            urllib.error.HTTPError(
                "https://graph.microsoft.com/x", 401, "Unauthorized", {}, None
            ),
            "unauthorized",
        ),
        (
            urllib.error.HTTPError(
                "https://graph.microsoft.com/x", 429, "Too Many", {}, None
            ),
            "http_429",
        ),
        (urllib.error.URLError("timed out"), "network"),
        (TimeoutError("timed out"), "network"),
    ]
    for boom, code in cases:

        def fake_urlopen(req, timeout=None, _b=boom):
            raise _b

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        with pytest.raises(OutlookError) as ei:
            OutlookClient._http_get_default(
                "https://graph.microsoft.com/x", "AT", "Europe/Rome"
            )
        assert ei.value.code == code, code


def test_outlook_error_text_codici_failure():
    """C5: 401/timeout hanno testo dedicato, 429 resta generico visibile."""
    from src.screens._shared import outlook_error_text

    assert outlook_error_text("unauthorized") != outlook_error_text("network")
    assert "429" in outlook_error_text("http_429")
    assert outlook_error_text("need_lock") != ""
