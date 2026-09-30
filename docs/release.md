# Release flow

Sequenza garantita:

```text
commit
 ↓
CI (ruff + format + mypy + pytest + build-smoke da wheel)
 ↓
all checks green sullo stesso SHA
 ↓
GitHub Release (tag vX.Y.Z)
 ↓
Publish workflow: gate rieseguito sul tag → build → smoke → PyPI
```

Regole:

- `publish.yml` non pubblica mai senza il job `gate` verde sullo stesso
  `ref` della release (`release.tag_name` o `sha` per i dispatch).
- Il job `build` di publish ricontrolla gli artifact (wheel + sdist),
  li installa in un venv pulito e lancia `carpediem --help` + import
  smoke prima dell'upload.
- Il job `publish-pypi` usa `environment: pypi`: su GitHub si possono
  aggiungere protection rules / required reviewers per l'environment.
- Il dispatch manuale verso `pypi` passa per lo stesso gate; per le prove
  usare `testpypi`.
- La versione in `pyproject.toml` deve già contenere tutto ciò che la
  release pubblica (bump nel commit di release, vedi `AGENTS.md` §6).
