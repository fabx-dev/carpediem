# ADR-002 — Concorrenza storage: lock + merge three-way

- Stato: accettato.
- Contesto: TUI e CLI (e due processi) scrivono gli stessi file JSON.
- Decisione: lock inter-processo per-file (fcntl/msvcrt, timeout 10s) +
  `store.commit()` come unico punto di scrittura con merge three-way
  sotto un solo lock. Regola di conflitto: vince chi salva; cancellato
  vs modificato vince la modifica (documentato in
  `tests/test_merge_invariants.py`).
- Alternative scartate: SQLite (migrazione dati + dipendenza), file per
  task (complessità), last-writer-wins cieco (perde dati).
