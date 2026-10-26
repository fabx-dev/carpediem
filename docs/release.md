# Release flow

Sequenza garantita:

```text
commit
 ↓
CI (ruff + format + mypy + pytest + build-smoke da wheel) + Snap CI (snap.yml)
 ↓
all checks green sullo stesso SHA
 ↓
GitHub Release (tag vX.Y.Z)
 ↓
Publish workflow (publish.yml): gate rieseguito sul tag → build → smoke → PyPI
Snap Release workflow (snap-release.yml): gate + snap build + smoke sul tag → Snap Store (stable)
```

Regole:

- `publish.yml` non pubblica mai senza il job `gate` verde sullo stesso
  `ref` della release (`release.tag_name` o `sha` per i dispatch).
- `snap-release.yml` riutilizza `.github/workflows/snap.yml` sullo stesso
  tag della release (`release.tag_name`), verificando corrispondenza
  `v<pyproject.toml version> == <tag>`, lint, mypy, pytest, build Snap
  (`core24`, strict confinement) e smoke test del pacchetto `.snap`
  installato prima di pubblicare sul canale `stable` dello Snap Store
  (dietro `environment: snap-store` e secret `SNAPCRAFT_STORE_CREDENTIALS`,
  vedi `docs/snap.md`).
- Il job `build` di publish ricontrolla gli artifact (wheel + sdist),
  li installa in un venv pulito e lancia `carpediem --help` + import
  smoke prima dell'upload.
- Il job `publish-pypi` usa `environment: pypi`: su GitHub si possono
  aggiungere protection rules / required reviewers per l'environment.
- Il dispatch manuale verso `pypi` passa per lo stesso gate; per le prove
  usare `testpypi`.
- La versione in `pyproject.toml` deve già contenere tutto ciò che la
  release pubblica (bump nel commit di release, vedi `AGENTS.md` §6).
