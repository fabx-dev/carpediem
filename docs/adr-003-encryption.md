# ADR-003 — Cifratura: Fernet + PBKDF2, chiave solo in RAM

- Stato: accettato.
- Contesto: dati personali su disco, senza server né portachiavi di sistema
  (cross-platform, offline-first).
- Decisione: envelope JSON `{"v","salt","data"}` con Fernet; chiave
  derivata per-file (salt dedicato), mai persistita; cache KDF in RAM
  (`lru_cache(8)`, vedi `docs/security.md`); token OAuth in file separato
  `0600` escluso dai backup; fail-closed senza chiave.
- Alternative scartate: portachiavi OS (non uniforme Linux/Windows),
  cifratura a livello backup (esporrebbe i file live).
