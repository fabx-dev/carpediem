"""Auth e fetch Outlook/Microsoft 365: unico punto di rete dell'integrazione.

Disegno sicurezza-max:
- public client MSAL, auth-code + PKCE con redirect loopback (il flusso
  raccomandato per le app native, RFC 8252): password/2FA mai viste da
  noi, solo nel browser (sistema o URL copiato a mano); niente
  client-secret (niente segreto da rubare);
- listener SOLO su 127.0.0.1 con porta effimera (mai 0.0.0.0, mai
  `localhost` come hostname: puo' risolvere a ::1 mentre il socket e'
  IPv4); chiuso sempre (anche su Esc via cancel);
- authority pinnata al tenant di config (`common` rifiutato in validazione),
  scope congelato `GRAPH_SCOPES`, endpoint solo `GRAPH_BASE_URL`;
- account binding: l'username del token deve coincidere con quello in
  config (se vuoto al primo login, si adotta quello autenticato);
- token-cache MSAL cifrata a riposo via storage (file 0600, mai backup/log);
- HTTP con sola stdlib `urllib` (nessuna nuova dipendenza oltre `msal`),
  timeout esplicito, errori mappati in codici (mai token negli errori).

Niente stato globale: `OutlookClient` riceve client/cache/http/listener/
opener iniettabili (i test usano doppi, mai rete/account reali). Le screen
non importano mai questo modulo: lo usa l'app via callback.
"""

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from src.integrations.outlook import (
    GRAPH_BASE_URL,
    GRAPH_SCOPES,
    LOGIN_AUTHORITY,
    parse_graph_events,
)
from src.storage import delete_outlook_token, load_outlook_token, save_outlook_token

HTTP_TIMEOUT = 15
CALENDAR_TOP = 50

#: Attesa del callback dal browser (login + 2FA: generoso, Esc annulla).
LOOPBACK_TIMEOUT = 180
#: Solo loopback IPv4 esplicito (mai 0.0.0.0, mai hostname ambiguo).
LOOPBACK_HOST = "127.0.0.1"
LOOPBACK_PATH = "/callback"


class OutlookError(Exception):
    """Errore integrazione con codice stabile per la UI (mai token dentro)."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def _open_browser_default(url: str) -> bool:
    """Apre il browser di sistema; False = l'utente copiera' l'URL a mano."""
    try:
        return bool(webbrowser.open(url, new=1, autoraise=True))
    except Exception:
        return False


class _CallbackHandler(BaseHTTPRequestHandler):
    """Un solo GET /callback: code o error, poi risposta di cortesia."""

    def do_GET(self) -> None:
        try:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != LOOPBACK_PATH:
                self.send_response(404)
                self.end_headers()
                return
            qs = urllib.parse.parse_qs(parsed.query)
            codes = qs.get("code") or []
            errs = qs.get("error") or []
            self.server.auth_result = {  # type: ignore[attr-defined]
                "code": codes[0] if codes else None,
                "error": errs[0] if errs else None,
            }
            self.server.got_result.set()  # type: ignore[attr-defined]
            body = "Login completato: puoi chiudere questa pagina e tornare a CarpeDiem.".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *args) -> None:
        pass  # mai log (l'URL contiene code/state: niente su disco/stdout)


class LoopbackListener:
    """Callback OAuth su 127.0.0.1:porta effimera, un solo uso, sempre chiuso.

    `server_cls` iniettabile per i test (mai rete reale nei test).
    """

    def __init__(self, server_cls=None) -> None:
        cls: Any = server_cls or HTTPServer
        try:
            self._server: Any = cls((LOOPBACK_HOST, 0), _CallbackHandler)
        except OSError as exc:
            raise OutlookError("loopback_bind_failed", str(exc)[:120])
        self._server.auth_result = None
        self._server.got_result = threading.Event()
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self._closed = False

    @property
    def redirect_uri(self) -> str:
        return f"http://{LOOPBACK_HOST}:{self.port}{LOOPBACK_PATH}"

    def wait(self, timeout: float = LOOPBACK_TIMEOUT) -> str:
        """Blocca fino al callback; ritorna il code (o solleva codificato)."""
        try:
            ok = self._server.got_result.wait(timeout)
        finally:
            self.close()
        if not ok:
            raise OutlookError("loopback_timeout")
        res = self._server.auth_result or {}
        if res.get("error") or not res.get("code"):
            raise OutlookError("authcode_denied", str(res.get("error") or "")[:120])
        return str(res["code"])

    def close(self) -> None:
        """Chiude il socket (idempotente, thread-safe: va chiamata su Esc)."""
        if self._closed:
            return
        self._closed = True
        try:
            self._server.shutdown()
        except Exception:
            pass
        try:
            self._server.server_close()
        except Exception:
            pass


class OutlookClient:
    """Adapter autenticato: silent -> auth-code/browser -> fetch -> parse."""

    def __init__(
        self,
        cfg: dict,
        client=None,
        cache=None,
        http_get=None,
        listener_factory=None,
        opener=None,
    ) -> None:
        self.cfg = dict(cfg)
        self._client = client
        self._cache = cache if cache is not None else self._new_cache()
        self._http_get = http_get or self._http_get_default
        self._listener_factory = listener_factory
        self._opener = opener
        stored = load_outlook_token()
        if stored and hasattr(self._cache, "deserialize"):
            try:
                self._cache.deserialize(stored)
            except Exception:
                pass

    @staticmethod
    def _new_cache():
        from msal import SerializableTokenCache  # type: ignore[import-untyped]

        return SerializableTokenCache()

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        try:
            from msal import PublicClientApplication  # type: ignore[import-untyped]
        except ImportError:
            raise OutlookError("msal_missing")
        authority = LOGIN_AUTHORITY.format(tenant=self.cfg.get("tenant", ""))
        self._client = PublicClientApplication(
            str(self.cfg.get("client_id", "")),
            authority=authority,
            token_cache=self._cache,
        )
        return self._client

    def _account(self):
        """Account MSAL bound a config (None = nessun vincolo possibile)."""
        client = self._ensure_client()
        try:
            accounts = client.get_accounts() or []
        except Exception as exc:
            raise OutlookError("msal_error", str(exc)[:120])
        want = str(self.cfg.get("account", "") or "").lower()
        if want:
            for acc in accounts:
                if str(acc.get("username", "")).lower() == want:
                    return acc
            return None
        return accounts[0] if len(accounts) == 1 else None

    def token_silent(self) -> tuple[str | None, str]:
        """(access_token|None, adopted_account): mai interattivo, mai solleva."""
        acc = self._account()
        if acc is None:
            return None, ""
        try:
            result = self._ensure_client().acquire_token_silent(
                list(GRAPH_SCOPES), account=acc
            )
        except Exception as exc:
            raise OutlookError("msal_error", str(exc)[:120])
        if not result or "access_token" not in result:
            return None, ""
        username = str(
            (result.get("id_token_claims") or {}).get("preferred_username", "")
            or acc.get("username", "")
        )
        want = str(self.cfg.get("account", "") or "")
        if want and username.lower() != want.lower():
            raise OutlookError("account_mismatch", username)
        return result["access_token"], username

    def authcode_start(self) -> dict:
        """Apre il browser sul login MS; ritorna {uri, browser_opened, handle}.

        `handle` e' opaco (flow + listener + redirect): va ripassato a
        `authcode_finish` o `cancel_authcode`. Se il browser non si apre,
        l'utente copia `uri` a mano (mai errore fatale qui).
        """
        client = self._ensure_client()
        factory = self._listener_factory or LoopbackListener
        try:
            listener = factory()
        except OutlookError:
            raise
        except Exception as exc:
            raise OutlookError("loopback_bind_failed", str(exc)[:120])
        redirect_uri = listener.redirect_uri
        account = str(self.cfg.get("account", "") or "") or None
        try:
            flow = client.initiate_auth_code_flow(
                scopes=list(GRAPH_SCOPES),
                redirect_uri=redirect_uri,
                login_hint=account,
            )
        except Exception as exc:
            listener.close()
            raise OutlookError("msal_error", str(exc)[:120])
        auth_uri = str((flow or {}).get("auth_uri", ""))
        if not auth_uri.startswith("https://"):
            listener.close()
            raise OutlookError("bad_auth_uri")
        opener = self._opener or _open_browser_default
        try:
            opened = bool(opener(auth_uri))
        except Exception:
            opened = False
        handle = {"flow": flow, "listener": listener, "redirect_uri": redirect_uri}
        return {"uri": auth_uri, "browser_opened": opened, "handle": handle}

    def authcode_finish(self, handle, timeout: float = LOOPBACK_TIMEOUT):
        """Attende il callback, scambia il code, ritorna (token, username)."""
        flow = handle.get("flow") if isinstance(handle, dict) else None
        listener = handle.get("listener") if isinstance(handle, dict) else None
        redirect_uri = (
            handle.get("redirect_uri", "") if isinstance(handle, dict) else ""
        )
        if flow is None or listener is None:
            raise OutlookError("generic", "expired")
        code = listener.wait(timeout)
        client = self._ensure_client()
        try:
            result = client.acquire_token_by_authorization_code(
                code, scopes=list(GRAPH_SCOPES), redirect_uri=redirect_uri or None
            )
        except Exception as exc:
            raise OutlookError("msal_error", str(exc)[:120])
        if not result or "access_token" not in result:
            raise OutlookError(
                "authcode_failed", str((result or {}).get("error", ""))[:120]
            )
        username = str(
            (result.get("id_token_claims") or {}).get("preferred_username", "")
        )
        want = str(self.cfg.get("account", "") or "")
        if want and username.lower() != want.lower():
            raise OutlookError("account_mismatch", username)
        self.save_cache()
        return result["access_token"], username

    def cancel_authcode(self, handle) -> None:
        """Chiude il listener (Esc in setup): niente thread/socket orfani."""
        try:
            listener = handle.get("listener") if isinstance(handle, dict) else None
        except Exception:
            return
        if listener is None:
            return
        try:
            listener.close()
        except Exception:
            pass

    def save_cache(self) -> None:
        """Persiste la cache (cifrata 0600 via storage)."""
        try:
            blob = self._cache.serialize()
        except Exception as exc:
            raise OutlookError("cache_error", str(exc)[:120])
        save_outlook_token(blob)

    def fetch_day(self, token: str, day_s: str):
        """(eventi, allday, scartati) del giorno via calendarView."""
        from datetime import datetime, timedelta

        try:
            day = datetime.strptime(day_s, "%Y-%m-%d")
        except (ValueError, TypeError):
            raise OutlookError("bad_day", day_s)
        lo = day.strftime("%Y-%m-%dT00:00:00")
        hi = (day + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00")
        query = urllib.parse.urlencode(
            {
                "startDateTime": lo,
                "endDateTime": hi,
                "$select": "subject,start,end,showAs,isAllDay",
                "$orderby": "start/dateTime",
                "$top": str(CALENDAR_TOP),
            }
        )
        url = f"{GRAPH_BASE_URL}/me/calendarview?{query}"
        try:
            payload = self._http_get(
                url, token, str(self.cfg.get("tz") or "Europe/Rome")
            )
        except OutlookError:
            raise
        except Exception as exc:
            raise OutlookError("network", str(exc)[:120])
        if not isinstance(payload, dict) or not isinstance(payload.get("value"), list):
            raise OutlookError("bad_payload")
        return parse_graph_events(
            payload, day_s, tz=str(self.cfg.get("tz") or "Europe/Rome")
        )

    @staticmethod
    def _http_get_default(url: str, token: str, tz: str) -> dict:
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Prefer": f'outlook.timezone="{tz}"',
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise OutlookError("unauthorized")
            if exc.code == 403:
                raise OutlookError("admin_consent")
            raise OutlookError(f"http_{exc.code}")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise OutlookError("network", str(exc)[:120])


def disconnect() -> None:
    """Disconnessione: cancella il token locale (revoca lato MS dai link in UI)."""
    delete_outlook_token()
