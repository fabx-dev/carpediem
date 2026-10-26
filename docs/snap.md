# Snap Packaging and Automated Release Guide

This document describes how CarpeDiem is packaged as a strictly confined Ubuntu Snap (`snap/snapcraft.yaml`), how data and confinement paths work at runtime, how to build and test the Snap locally, and how the GitHub Actions CI/CD pipelines (`snap.yml` and `snap-release.yml`) validate and publish versioned releases to the Snap Store.

> **Status note**: The `carpediem` Snap is published on the Snap Store (`stable` channel, first published with v0.22.0 on 2026-10-26): install it with `sudo snap install carpediem`. The one-time Store name registration and `SNAPCRAFT_STORE_CREDENTIALS` setup below are already completed by the maintainer.

---

## 1. Snap Architecture and Confinement

- **Snap name**: `carpediem`
- **Base**: `core24` (Ubuntu 24.04 LTS, providing Python 3.12 natively, matching `requires-python = ">=3.12"` in `pyproject.toml`)
- **Confinement**: `strict` (`grade: stable`)
- **Single version source**: `snap/snapcraft.yaml` uses `adopt-info: carpediem` and extracts the version dynamically from `pyproject.toml` during `override-pull` via `craftctl set version="$version"`. No independent version string is maintained in `snap/snapcraft.yaml`.
- **Exposed command**: `carpediem` (`apps.carpediem.command: bin/carpediem`), supporting both interactive TUI mode (`carpediem`) and non-interactive CLI subcommands (`carpediem add|list|done|show|replan`).
- **Declared plugs**:
  - `home`: auto-connected on Ubuntu Desktop/Classic; allows importing/exporting CSV files in non-hidden directories under the user's home directory and reading legacy `~/Tasko_backups/` archives.
  - `network`: auto-connected; used only when the user explicitly opts into Microsoft Outlook calendar synchronization. Core task management and planning remain 100% offline.
  - `network-bind`: auto-connected; used only by `LoopbackListener` (`127.0.0.1:<ephemeral_port>`) to receive the OAuth 2.0 Authorization Code + PKCE redirect callback from the local browser during Outlook login.

---

## 2. Data Paths, Persistence, and Migration Under Confinement

### Default Writable Paths Inside the Snap

When running inside the strictly confined Snap (where `snapd` sets `SNAP_USER_COMMON`), CarpeDiem stores all persistent state under `$SNAP_USER_COMMON` (`~/snap/carpediem/common`):

| Path | Purpose |
| --- | --- |
| `~/snap/carpediem/common/.config/carpediem/config.json` | User settings, theme, language, capacity (`day_hours`), smart lists, confirmed `day_window`, Outlook non-secret config |
| `~/snap/carpediem/common/.local/share/carpediem/todos.json` | Active, paused, and completed tasks (with `.bak.json` / `.bak.1.json` rotation and `.lock` sidecars) |
| `~/snap/carpediem/common/.local/share/carpediem/templates.json` | Task templates |
| `~/snap/carpediem/common/.local/share/carpediem/pomodoro.json` | Persistent Pomodoro timer state and cycle counter |
| `~/snap/carpediem/common/.local/share/carpediem/archive.json` | Archived tasks |
| `~/snap/carpediem/common/.local/share/carpediem/executions.json` | Task execution history for pace calibration |
| `~/snap/carpediem/common/.local/share/carpediem/outlook-token.json` | Encrypted MSAL token cache (`0600`, excluded from backups) |
| `~/snap/carpediem/common/.local/share/carpediem/backups/carpediem_*.zip` | Automatic state snapshots (14 retained) |
| `~/snap/carpediem/common/CarpeDiem_screenshots/` | SVG screenshots, Markdown exports, CSV exports, stats CSV exports, and iCal (`.ics`) exports |

### Why `SNAP_USER_COMMON` Is Used

1. **Survives restarts and `snap refresh`**: Unlike `SNAP_USER_DATA` (`~/snap/carpediem/<revision>`), which is copied into a new directory on every revision upgrade, `SNAP_USER_COMMON` (`~/snap/carpediem/common`) is shared across all revisions. Tasks, configuration, exports, and zip backups remain in one place across restarts, upgrades, and rollbacks without duplicating backup archives across revisions.
2. **Immune to host `XDG_*` dotfile restrictions**: Under Snap `strict` confinement, AppArmor blocks access to top-level hidden directories in the user's real home (`~/.config` and `~/.local/share`), even when the `home` interface is connected. `carpediem.storage` checks `SNAP_USER_COMMON` (and `snap/snapcraft.yaml` sets `XDG_CONFIG_HOME` / `XDG_DATA_HOME` to `$SNAP_USER_COMMON/.config` and `$SNAP_USER_COMMON/.local/share`), preventing `PermissionError` if the host shell exports `XDG_CONFIG_HOME` or `XDG_DATA_HOME`.
3. **Never writes to `$SNAP`**: The squashfs installation directory (`/snap/carpediem/current`) is strictly read-only.

### Environment Overrides (`CARPEDIEM_HOME`, `TASKO_HOME`, `CARPEDIEM_LANG`)

- `CARPEDIEM_HOME` (and legacy alias `TASKO_HOME`) still takes top precedence over `SNAP_USER_COMMON`.
- Note on Snap confinement when using `CARPEDIEM_HOME`:
  - Inside a strictly confined Snap, `/tmp` is a private per-snap mount namespace (`/tmp/snap-private-tmp/snap.carpediem/tmp` on the host) and top-level hidden directories in `$HOME` (`~/.my-dir`) are blocked by AppArmor.
  - Point `CARPEDIEM_HOME` to a path inside `~/snap/carpediem/common/...` or a non-hidden directory in your real home (e.g., `CARPEDIEM_HOME="$HOME/carpediem-demo" carpediem` when the `home` plug is connected).
- `CARPEDIEM_LANG=it|en` (and legacy alias `TASKO_LANG`) works unchanged.

### Migrating Data from an Existing `pipx` / `pip` Installation

Because Snap `strict` confinement forbids reading top-level hidden directories (`~/.config/carpediem` and `~/.local/share/carpediem`) in the host home without a privileged `personal-files` interface, a newly installed Snap cannot automatically read `~/.local/share/carpediem` from a prior `pipx` or `pip` install.

To migrate existing `pipx`/`pip` data into the Snap without losing any state:

```bash
mkdir -p ~/snap/carpediem/common/.config ~/snap/carpediem/common/.local/share
cp -rn ~/.config/carpediem ~/snap/carpediem/common/.config/
cp -rn ~/.local/share/carpediem ~/snap/carpediem/common/.local/share/
```

Notes on automatic migration inside Snap:
- If an earlier Snap run stored files under `$SNAP_USER_DATA` (`~/snap/carpediem/<rev>/.local/share/carpediem` or `.config/carpediem`), `migrate_legacy()` automatically copies them byte-identically into `~/snap/carpediem/common/` on startup (verified, idempotent, never overwriting existing files).
- If legacy `~/Tasko_backups/tasko_*.zip` exists in the real home directory and the `home` interface is connected, `migrate_legacy()` copies those backup archives into `~/snap/carpediem/common/.local/share/carpediem/backups/`.

---

## 3. Confinement Limitations and Feature Notes

- **Filesystem access**: Reading CSV files for import (`Import: CSV`) works for files in `~/snap/carpediem/common/CarpeDiem_screenshots/` or any non-hidden directory under `/home/<user>/` (such as `/home/<user>/Downloads/`) when the `home` interface is connected. Files inside hidden host directories (`/home/<user>/.hidden/...`) or outside `/home/<user>/` cannot be read by the confined Snap.
- **Private `/tmp`**: Files written to `/tmp` inside the Snap live in the Snap's private `/tmp` namespace and are not visible in the host's `/tmp`.
- **Outlook OAuth2 browser launch**: During Outlook setup (`OutlookSetupScreen`), CarpeDiem attempts to open the Microsoft login URL via `webbrowser.open()` (which uses Snapd's `xdg-open` portal on desktop systems) and listens on `http://127.0.0.1:<ephemeral_port>/callback`. On headless servers or environments where browser forwarding is unavailable, CarpeDiem displays the full `https://` login URL in the modal so you can copy and open it manually in any local browser.

---

## 4. Building and Testing the Snap Locally

### Option A: Using Snapcraft with LXD or Multipass (Ubuntu / Linux with `snapd`)

1. Install Snapcraft and LXD:
   ```bash
   sudo snap install snapcraft --classic
   sudo snap install lxd
   sudo lxd init --auto
   ```
2. Build the Snap from the repository root:
   ```bash
   snapcraft pack --verbosity=verbose
   ```
   This produces `carpediem_<version>_amd64.snap` (e.g., `carpediem_0.21.1_amd64.snap`).

### Option B: Using the Official Canonical Snapcraft Container (Docker, No `snapd` Required)

On systems without `snapd` or LXD (such as WSL2 or non-Ubuntu distributions), build the Snap using Canonical's official `core24` Snapcraft container image:

```bash
docker run --rm -v "$PWD":/project -w /project \
  ghcr.io/canonical/snapcraft:8_core24 pack --verbosity=verbose
```

### Installing and Smoke-Testing the Built `.snap` Locally

On a system with `snapd` running:

1. Install the locally built `.snap` with `--dangerous` (required because a local `.snap` has not yet been signed by the Snap Store; it still runs under full `strict` confinement):
   ```bash
   sudo snap install --dangerous ./carpediem_0.21.1_amd64.snap
   ```
2. Check installed metadata and interface connections:
   ```bash
   snap list carpediem
   snap connections carpediem
   ```
3. Smoke-test non-interactive CLI commands and persistence:
   ```bash
   carpediem --help
   carpediem add "Verify snap install tomorrow #snap *ops !high ~2"
   carpediem list --porcelain
   carpediem show 1
   carpediem replan --now 09:00
   carpediem done 1
   ls -la ~/snap/carpediem/common/.local/share/carpediem/
   ```
4. Launch the interactive TUI:
   ```bash
   carpediem
   ```
   Verify keyboard navigation (`P` Buongiorno, `p` Day plan, `R` Day closing, `m` Menu, `ctrl+e` Markdown export, `q` Quit).

---

## 5. Installing from the Snap Store (Once Published)

Once the maintainer has registered the Snap name and published the first release:

```bash
sudo snap install carpediem
```

To test a pre-release channel (`edge`, `beta`, or `candidate`):

```bash
sudo snap install carpediem --channel=edge
```

---

## 6. CI/CD Workflows: Development Builds vs. Stable Releases

Two workflows manage Snap builds and releases:

### 1. `.github/workflows/snap.yml` (`Snap CI`)

- **Triggers**:
  - `pull_request` targeting `main`
  - `push` to `main`
  - `workflow_dispatch` (manual run)
  - `workflow_call` (reused by `snap-release.yml`)
- **What it does**:
  1. **Job `gate`**: Checks out the target commit, sets up Python 3.12, validates `snap/snapcraft.yaml` and tag/version consistency against `pyproject.toml`, installs `requirements-dev.txt`, and runs `ruff check`, `ruff format --check`, `mypy src/`, and `pytest` with the `--cov-fail-under=75` coverage gate.
  2. **Job `build-snap`**: Builds the `.snap` package via `canonical/action-build`, verifies the embedded `meta/snap.yaml` version and `strict` confinement settings, installs the `.snap` on the runner (`sudo snap install --dangerous`), executes CLI, persistence, override, headless Textual TUI, encryption, and Outlook `LoopbackListener` smoke tests inside the confined Snap sandbox, and uploads `carpediem-snap-<version>` as a workflow artifact.
  3. **Failure diagnostics**: If the build fails, Snapcraft and LXD logs are automatically collected and uploaded as `snap-build-diagnostics-<run_id>`.
- **Security**: `snap.yml` never accesses `SNAPCRAFT_STORE_CREDENTIALS` and never publishes to the Snap Store. Pull requests can never publish packages.

### 2. `.github/workflows/snap-release.yml` (`Snap Release`)

- **Triggers**:
  - `release: types: [published]` (automatically publishes to the `stable` channel when a non-draft, non-prerelease GitHub Release is published)
  - `workflow_dispatch` (manual release of a specified tag `vX.Y.Z` to a chosen channel: `stable`, `candidate`, `beta`, or `edge`)
- **What it does**:
  1. Calls `.github/workflows/snap.yml` on the exact release tag (`ref: ${{ github.event.release.tag_name }}`), ensuring all unit tests, linters, type checks, Snap build, and Snap installation smoke tests pass on the tagged commit.
  2. In the `publish-snap` job (protected by `environment: snap-store`), checks out the tagged commit, downloads the verified `.snap` artifact, re-verifies SHA-256 integrity and `v<pyproject.toml version> == <tag>`, checks that `SNAPCRAFT_STORE_CREDENTIALS` is configured, publishes to the Snap Store via `canonical/action-publish`, and logs the published revision and channel status in the workflow summary.

---

## 7. Maintainer Setup: Snap Store Registration and GitHub Secrets

Before the first automated release can publish to the Snap Store, the maintainer must perform these one-time steps:

### Step 1: Register the `carpediem` Snap Name

1. Create an Ubuntu One / Snapcraft developer account at <https://snapcraft.io/>.
2. On a local machine with `snapcraft` installed, log in and register the name:
   ```bash
   snapcraft login
   snapcraft register carpediem
   ```
   *(Alternatively, register `carpediem` from the web dashboard at <https://snapcraft.io/snaps>.)*

### Step 2: Export Scoped Store Credentials

Generate attenuate credentials locked down to the `carpediem` snap and only the required store ACLs (`package_access`, `package_push`, `package_update`, `package_release`):

```bash
snapcraft export-login --snaps=carpediem \
  --acls package_access,package_push,package_update,package_release \
  snapcraft-credentials.txt
```

> **Security warning**: Never commit `snapcraft-credentials.txt` to git. Delete the local file immediately after copying its contents into GitHub Secrets (`shred -u snapcraft-credentials.txt` or `rm -f snapcraft-credentials.txt`).

### Step 3: Configure the `snap-store` GitHub Environment and Secret

1. In the GitHub repository (`https://github.com/fabx-dev/carpediem`), open **Settings → Environments**.
2. Click **New environment** and name it **`snap-store`**.
3. *(Recommended)* Configure protection rules on `snap-store`:
   - Enable **Required reviewers** if you want manual approval before publishing to the Snap Store.
   - Under **Deployment branches and tags**, restrict deployments to tags matching `v*` (or `Protected branches only`).
4. Under **Environment secrets** inside `snap-store`, click **Add environment secret**:
   - **Name**: `SNAPCRAFT_STORE_CREDENTIALS`
   - **Value**: Paste the full contents of `snapcraft-credentials.txt`.
5. Remove the temporary local file:
   ```bash
   rm -f snapcraft-credentials.txt
   ```

---

## 8. Creating a Versioned Release

Following the repository's release convention (`AGENTS.md` §6 and `docs/release.md`):

1. Ensure all feature commits are merged on `main` and listed under `## [Unreleased]` in `CHANGELOG.md`.
2. In a release commit (`chore(release): bump to X.Y.Z`):
   - Update `version = "X.Y.Z"` in `pyproject.toml` (the single authoritative version source; `snap/snapcraft.yaml` adopts this version automatically).
   - Date the `## [X.Y.Z] - YYYY-MM-DD` section in `CHANGELOG.md` and reopen an empty `## [Unreleased]`.
3. Push `main` and wait for both **CI** (`ci.yml`) and **Snap CI** (`snap.yml`) to succeed on that commit SHA:
   ```bash
   git push origin main
   gh run list --limit 5
   ```
4. Create and publish the GitHub Release with tag `vX.Y.Z`:
   ```bash
   gh release create vX.Y.Z --title "vX.Y.Z" --notes-from-tag
   ```
5. Publishing the GitHub Release triggers:
   - `Publish` (`publish.yml`) → publishes wheel and sdist to PyPI.
   - `Snap Release` (`snap-release.yml`) → builds and publishes `carpediem_X.Y.Z_amd64.snap` to the Snap Store `stable` channel.

---

## 9. Inspecting CI Logs and Troubleshooting

- **Inspect workflow runs**:
  ```bash
  gh run list --workflow="Snap CI"
  gh run list --workflow="Snap Release"
  gh run view <run-id> --log-failed
  ```
- **Download failure diagnostics**:
  When `build-snap` fails, download the `snap-build-diagnostics-<run-id>` artifact from the workflow run summary (or via `gh run download <run-id> -n snap-build-diagnostics-<run-id>`), which contains `~/.local/state/snapcraft/log/*.log` and LXD daemon logs.
- **Common failure causes**:
  - **`Release tag 'vX.Y.Z' does not match pyproject.toml version`**: Ensure the Git tag starts with `v` and matches `project.version` in `pyproject.toml` (`v0.21.1` ↔ `0.21.1`).
  - **`SNAPCRAFT_STORE_CREDENTIALS is not set or is empty`**: Verify the secret is named `SNAPCRAFT_STORE_CREDENTIALS` inside the `snap-store` GitHub Environment (or Repository Secrets) and that the workflow run is authorized to access the `snap-store` environment.
  - **Expired or insufficient Store credentials**: Re-run `snapcraft export-login --snaps=carpediem --acls package_access,package_push,package_update,package_release -` and update the `SNAPCRAFT_STORE_CREDENTIALS` secret.
