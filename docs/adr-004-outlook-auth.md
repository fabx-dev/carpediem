# ADR-004 — Auth Outlook: public client, auth-code + PKCE loopback

- Stato: accettato.
- Contesto: leggere il calendario MS365 senza server e senza segreti
  custoditi.
- Decisione: MSAL public client (niente client-secret), auth-code + PKCE
  con callback su `127.0.0.1` a porta effimera (mai `0.0.0.0`, mai hostname
  `localhost`), authority pinnata al tenant di config (mai `common`),
  scope congelato `Calendars.Read`, account binding, timeout 180s,
  token-cache `0600` fuori dai backup/log. Rete solo in
  `src/integrations/outlook_auth.py` (doppi iniettabili; screen mai rete).
- Regression blindate in `tests/test_outlook_security.py`.
