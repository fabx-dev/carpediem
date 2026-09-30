# Dipendenze: policy vs lock

Due livelli separati:

- **Policy** (`requirements.txt`, intervalli): cosa è compatibile.
  Modificarla quando si allarga/restringe il supporto (es. `textual<5`).
- **Lock** (`requirements.lock`, pin esatti): ambiente deterministico
  della release. Ricostruibile con:

```bash
python -m venv /tmp/relock
/tmp/relock/bin/pip install -r requirements.lock
/tmp/relock/bin/pip install dist/*.whl  # oppure -e . per dev
```

Come aggiornare:

1. Cambia `requirements.txt` (o `pyproject.toml`, poi allinea).
2. `pip install -r requirements-dev.txt` in venv pulita, lancia la CI
   completa in locale (`pytest`, `ruff`, `mypy`).
3. Se verde: `pip freeze` filtrato sulle dipendenze runtime → riscrivi
   `requirements.lock`, committalo nella stessa release.
4. Mai pinnare a mano versioni non testate in CI.

Nota: `pyproject.toml` e `requirements.txt` devono restare allineati
(lezione CI 0.13.1: la CI installa da `requirements*.txt`).
