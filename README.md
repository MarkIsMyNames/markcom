# markcom

Shared libraries for my Python and TypeScript projects.

| Folder | Package | For |
|---|---|---|
| `markcom/` | `markcom` (Python, installed from git) | typed `config.json`, secrets from the environment and the `.env` beside `config.json`, logging and the `run()` entry point; with the `desktop` extra, notifications; with the `window` extra, a tray icon and a web frontend in its own window (`markcom.tray`, `markcom.window`); with the `web` extra, a loopback Host/Origin guard (`markcom.own_origin`); with the `nicegui` extra, a NiceGUI UI served on its own thread (`markcom.ui_server`, `markcom.page_refresh`) |
| `markcom-i18n/` | `@markcom/i18n` (npm) | locale lookup, browser-language detection, i18next set-up, the `index.html` locale plugin, `/<lang>/` routing, and build-time checks of every locale file; its `e2e/` tests the routing on a small test site |
| `markcom-web-config/` | `@markcom/web-config` (npm) | shared ESLint, Prettier, TypeScript and Vitest coverage settings |

## Installing

Python, pinned by release tag, with uv:

```toml
[project]
dependencies = ["markcom"]

[tool.uv.sources]
markcom = { git = "https://github.com/MarkIsMyNames/markcom", subdirectory = "markcom", tag = "markcom-v<version>" }
```

The `desktop` extra (`markcom[desktop]`) sends notifications and needs no Qt. The `window` extra (`markcom[window]`) adds the tray icon and `markcom.window`, which shows a web frontend in its own window with QtWebEngine; it downloads Qt and WebEngine, about 260 MB on Linux (pyside6-webengine, pyside6-addons and pyside6-essentials). The window keeps no cookies or site storage between runs, and it does not download files.

A tray built with `TrayNotifications` also sends every logger's ERROR records as notifications, shown for its `error_display_sec`, and CRITICAL ones until dismissed, while it is entered. Each counts on the tray's badge. An app logs a failure and markcom notifies; it needs no notifier code of its own.

The `web` extra (`markcom[web]`, Starlette only) adds `OwnOriginOnly`, ASGI middleware for a server bound to loopback: it refuses any request or websocket whose Host, or Origin if it has one, is not the server's own address, which stops DNS rebinding and cross-origin websockets from pages in the browser. The `nicegui` extra (`markcom[nicegui]`) adds `UiServer`, which serves a NiceGUI UI behind that guard on its own thread so the tray and window keep the main thread, and `keep_current`, which redraws a page's body when a change is announced (`announce`, safe from any thread, such as a scheduler's) and only if what it shows has changed.

TypeScript, from npm:

```sh
npm install @markcom/i18n
npm install --save-dev @markcom/web-config
```

## Shared repository settings

- **Renovate preset** (`default.json`): every repository's `renovate.json` is only `{"extends": ["github>MarkIsMyNames/markcom"]}`, so a rule changed here applies everywhere.
- **Security workflow** (`.github/workflows/security.yml`): Gitleaks and Semgrep. A CI workflow calls it with `uses: MarkIsMyNames/markcom/.github/workflows/security.yml@<commit sha> # main`, granting `contents: read` and `pull-requests: read`; Renovate keeps the commit up to date.

## Releasing

CI releases every library on its own, and is the only thing that changes a version. On every push to `main`, for each library whose code or install manifest changed since its last release:

1. CI picks the next version: a patch, or the next minor or major when the merged pull request has the `release:minor` or `release:major` label (the larger wins). From 0.x, `release:major` gives 1.0.0, so a breaking change below 1.0 takes `release:minor`.
2. CI commits that version to `main` as `chore(release): <library> <version>, …`, in `markcom/pyproject.toml` and `markcom/uv.lock`, or the package's `package.json` and `package-lock.json`.
3. CI tags that commit `<library>-v<version>` (`markcom-v…`, `markcom-web-config-v…`, `markcom-i18n-v…`) and publishes each npm package from its tag. Projects install `markcom` by its tag.

What counts:

| Library | Code | Install manifest |
|---|---|---|
| `markcom` | `markcom/src`, tests excluded | `[project]` (dependencies included), `[build-system]` and `[tool.hatch]` in `pyproject.toml` |
| `@markcom/web-config` | `src`, `tsconfig.json`, `prettier.json` | `package.json` without `devDependencies`, `overrides` and scripts other than build, publish and install ones |
| `@markcom/i18n` | `src`, tests excluded | as for web-config |

Tests, lock files, dev dependencies, tool settings and build settings release nothing. Never edit a version, run `npm publish` or push a `markcom-*` tag by hand: the `versions-unchanged` check fails a pull request that changes a version, and the release fails on a version that differs from the last release. CI signs in to npm by trusted publishing (OIDC), set up on each package's npm settings page for this repository and `ci.yml`, so no npm token is stored. The release logic lives in `release-tools/`.

## Checks

`pre-commit install` runs the same checks as CI before each commit; `pre-commit run --all-files` runs them on demand.

| Check | markcom (Python, uv) | markcom-i18n, markcom-web-config (TypeScript, npm) |
|---|---|---|
| Lint | `uv run ruff check .` | `npm run lint` (ESLint) |
| Format | `uv run ruff format --check .` | `npm run format:check` (Prettier) |
| Types | `uv run mypy src` | `npm run typecheck` (tsc) |
| Language scanner | `uv run bandit -q -r src -x '*_test.py'` | ESLint security rules, part of `npm run lint` |
| Audit | `uv run pip-audit --skip-editable` | `npm run audit` |
| Unit tests, 85% coverage gate | `uv run pytest -q` | `npm test` (Vitest; markcom-i18n only) |
| Integration tests (own CI job): Linux notifications over a private D-Bus session | `dbus-run-session -- uv run pytest tests/integration --no-cov -q` | none |
| End-to-end | none | `npm run test:e2e` (Playwright; markcom-i18n only) |

Gitleaks and Semgrep run across the whole repository.

## Licence

MIT, see `LICENSE`.
