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
- **Visual baselines workflow** (`.github/workflows/visual-baselines.yml`): started by hand on a pull request branch of a project with Storybook screenshot tests. It compares every screenshot with the default branch's baseline, commits only the images that differ, and lists them in the run summary. A push with `GITHUB_TOKEN` starts no workflows, so it starts the workflows the caller lists, each with a `workflow_dispatch` trigger. ClaudeSkills' react-ui template calls it.

## Releasing

CI releases every library `release.json` lists, each on its own, and is the only thing that changes a version. On every push to `main`, for each library whose code changed since its latest tag:

1. CI takes that tag and bumps it: a patch, or the next minor or major when the merged pull request has the `release:minor` or `release:major` label (the larger wins). A library with no tag yet is released at the version in its files. From 0.x, `release:major` gives 1.0.0, so a breaking change below 1.0 takes `release:minor`.
2. CI commits that version to `main` as `chore(release): <library> <version>, …`, in the library's `pyproject.toml` and `uv.lock`, or its `package.json` and `package-lock.json`.
3. CI tags that commit with the library's tag prefix (`markcom-v…`, `markcom-web-config-v…`, `markcom-i18n-v…`, `release-tools-v…`), creates a GitHub release, and publishes each npm package from its tag. Projects install `markcom` by its tag.

A library's code is its `src` folder (tests and `conftest.py` excluded), its manifest (`pyproject.toml` or `package.json`, any change) and the files `release.json` lists as `extra_code`: web-config's `tsconfig.json` and `prettier.json`, which projects extend directly. Tests, lock files and build settings such as i18n's `tsconfig.json` release nothing.

Never edit a version, run `npm publish` or push a release tag by hand: the `versions-unchanged` check fails a pull request that changes a version. The release job fails if `main` has moved past the commit it runs for; the run for the newest commit releases instead. CI signs in to npm by trusted publishing (OIDC), set up on each package's npm settings page for this repository and `ci.yml`, so no npm token is stored.

### Releasing another repository the same way

`release-tools/` is itself a library, released as `release-tools-v<version>`, and its two workflows are shared like the security workflow:

1. Add a `release.json` at the repository root listing its libraries. Each library has `name`, `kind` (`uv` or `npm`), `path` (its folder, `.` for the root), `tag_prefix` (for example `v`) and `extra_code` (files of its code outside `src`, usually `[]`).
2. Call `.github/workflows/versions-unchanged.yml` on every event but pushes and `.github/workflows/release.yml` on pushes to `main` after the checks, pinned to the commit of a `release-tools-v*` tag, as ClaudeSkills' base template's `ci.yml` does. The release workflow's `tags` output lists what it released, for publish or deploy jobs.
3. Create the `release:minor` and `release:major` labels (`gh label create`).

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
