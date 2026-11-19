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

CI releases exactly the version committed to the repository, so the two never differ. On every push to `main`:

- **markcom**: when `version` in `markcom/pyproject.toml` is higher than the last `markcom-v*` tag, CI tags the pushed commit `markcom-v<version>`.
- **npm packages**: when `version` in a `package.json` is higher than the latest on npm, CI publishes it. CI signs in to npm by trusted publishing (OIDC), set up on each package's npm settings page for this repository and `ci.yml`, so no npm token is stored.

A pull request that changes a library's shipped files must raise that library's version; the `version-raised` check fails otherwise. Shipped files are the library's source (tests excluded), `tsconfig.json` and `prettier.json` for the npm packages (`markcom-i18n`'s tsconfig extends `markcom-web-config`'s), and the parts of `pyproject.toml` or `package.json` an install reads. Tests, lock files, `devDependencies` (build tools included), `overrides`, `dependency-groups` and tool settings need no raise. After raising `markcom`'s version, run `uv lock`; after raising an npm package's, run `npm version <version> --no-git-tag-version` so `package-lock.json` matches.

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
