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

    def initiate_auth_code_flow(self, scopes, redirect_uri=None):
        self.scopes_seen = list(scopes)
        self.redirect_seen = redirect_uri
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
    assert closed == [True]
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
