# markcom

Shared libraries for my Python and TypeScript projects: `markcom` for Python, `@markcom/i18n` and `@markcom/web-config` for npm, and the release tool and CI workflows my other repositories call.

## Requirements

- Python 3.13 or later, with uv, for `markcom` and `release-tools`
- Node.js 24 or later, with npm, for `@markcom/i18n` and `@markcom/web-config`
- On Linux, a D-Bus session with a notification service, for `markcom[desktop]` notifications
- pre-commit, to run the checks

## Quick start

Python, pinned by release tag, with uv:

```toml
[project]
dependencies = ["markcom"]

[tool.uv.sources]
markcom = { git = "https://github.com/MarkIsMyNames/markcom", subdirectory = "markcom", tag = "markcom-v<version>" }
```

TypeScript, from npm:

```sh
npm install @markcom/i18n
npm install --save-dev @markcom/web-config
```

## Usage

### markcom

| Function or class | Extra | What it does | Example |
|---|---|---|---|
| `run` | none | Loads `config.json` and the secrets, configures logging at the config's `log_level`, then calls `main(config, secrets)`. A configuration error goes to stderr and exits with `os.EX_CONFIG`. | `run(main, Path("config.json"), AppConfig, AppSecrets)` |
| `BaseAppConfig` | none | Base for an app's `config.json` model, with `log_level`. Every field is required, unknown keys are rejected, and the model is immutable. | `class AppConfig(BaseAppConfig): poll_sec: int` |
| `BaseSecrets`, `NoSecrets` | none | Base for secrets: each field is read from its upper-case variable, from the environment first, then from the `.env` beside `config.json`. `NoSecrets` is for an app that reads none; it ignores any `.env`. | `class AppSecrets(BaseSecrets): api_token: SecretStr` |
| `DesktopNotifier` | `desktop` | Sends desktop notifications from the caller's thread. Needs no Qt. | `DesktopNotifier("App", icon)` |
| `Tray`, `TrayAction`, `TrayNotifications` | `window` | Tray icon. A left click opens or closes its target; a right click shows its actions, then Quit. | `with Tray(app, icon, None, window, [TrayAction("Sync", sync)]): app.exec()` |
| `WebWindow` | `window` | Shows a web frontend in its own window, with QtWebEngine, as the tray's target. | `WebWindow("App", url, icon)` |
| `OwnOriginOnly` | `web` | ASGI middleware for a server bound to loopback. | `OwnOriginOnly(app, IPv4Address("127.0.0.1"), 8080)` |
| `UiServer` | `nicegui` | Serves a NiceGUI UI behind `OwnOriginOnly` on its own thread, so the tray and window keep the main thread. | `with UiServer(root, "App", IPv4Address("127.0.0.1"), 8080): app.exec()` |
| `keep_current`, `announce` | `nicegui` | `keep_current` draws a page's body and redraws it when a change is announced, only if what it shows has changed. `announce` is safe from any thread, such as a scheduler's. | `refresh = keep_current(read, body, changed)` |

The `window` extra downloads Qt and WebEngine, about 260 MB on Linux (pyside6-webengine, pyside6-addons and pyside6-essentials). The window runs in its own process, started on each open and ended on each close, so a closed window holds no QtWebEngine memory. Each open loads the page afresh; the window keeps its size and maximised state in `~/.config/markcom/<title>.conf`. The window process's warnings and errors go to the app's stderr as bare messages, not to notifications. The window keeps no cookies or site storage, and it does not download files.

A tray built with `TrayNotifications` also sends every logger's ERROR records as notifications, shown for its `error_display_sec`, and CRITICAL ones until dismissed, while it is entered. Each counts on the tray's badge. An app logs a failure and markcom notifies; it needs no notifier code of its own.

`OwnOriginOnly` refuses any request or websocket whose Host, or Origin if it has one, is not the server's own address, which stops DNS rebinding and cross-origin websockets from pages in the browser.

### @markcom/i18n

| Import | What it does |
|---|---|
| `@markcom/i18n` | Locale lookup and browser-language detection (`LocaleSet`, `lookupString`) |
| `@markcom/i18n/i18next` | i18next set-up (`createI18n`) |
| `@markcom/i18n/vite` | The `index.html` locale plugin, which also checks every locale file at build time (`localeHtmlPlugin`) |
| `@markcom/i18n/react-router` | `/<lang>/` routing (`languageRoutes`) |
| `@markcom/i18n/vitest-setup` | A Vitest setup file in which `t()` returns each key unchanged |

Its `e2e/` tests the routing on a small test site.

### @markcom/web-config

| Import | What it does |
|---|---|
| `@markcom/web-config/eslint` | ESLint settings (`createEslintConfig`) |
| `@markcom/web-config/prettier` | Prettier settings |
| `@markcom/web-config/tsconfig.json` | TypeScript settings to extend |
| `@markcom/web-config/vitest` | Vitest coverage settings (`coverageGate`) |
| `@markcom/web-config/playwright` | Playwright settings (`createPlaywrightConfig`) and the test that screenshots every Storybook story (`testStoryScreenshots`) |
| `@markcom/web-config/storybook` | Storybook settings (`createStorybookConfig`) |

## Shared repository settings

- `default.json`, the Renovate preset: every repository's `renovate.json` is only `{"extends": ["github>MarkIsMyNames/markcom"]}`, so a rule changed here applies everywhere.
- `.github/workflows/security.yml`: Gitleaks and Semgrep. A CI workflow calls it with `uses: MarkIsMyNames/markcom/.github/workflows/security.yml@<commit sha> # main`, granting `contents: read` and `pull-requests: read`; Renovate keeps the commit up to date.
- `.github/workflows/ui-tests.yml`: for a project with Storybook, the accessibility check and the comparison of every story's screenshot with its committed baseline, on each push and pull request.
- `.github/workflows/visual-baselines.yml`: started by hand on a pull request branch after an intended visual change. It compares every screenshot with main's baseline, commits only the images that differ, and lists them in the run summary. A push with `GITHUB_TOKEN` starts no workflows, so it starts the workflows the caller lists, each with a `workflow_dispatch` trigger. ClaudeSkills' react-ui template calls both UI workflows.

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

## Commands

| Command | What it does |
|---|---|
| `pre-commit install` | Installs the hook that runs every check below before each commit, the same checks as CI |
| `pre-commit run --all-files` | Runs every check on demand |

Run each check inside its library's folder.

| Check | markcom, release-tools (Python, uv) | markcom-i18n, markcom-web-config (TypeScript, npm) |
|---|---|---|
| Lint | `uv run ruff check .` | `npm run lint` (ESLint) |
| Format | `uv run ruff format --check .` | `npm run format:check` (Prettier) |
| Types | `uv run mypy src` | `npm run typecheck` (tsc) |
| Language scanner | `uv run bandit -q -r src -x '*_test.py'`; release-tools: `uv run bandit -q -r src -c pyproject.toml` | ESLint security rules, part of `npm run lint` |
| Lock file up to date | `uv lock --check` | none |
| Audit | `uv run pip-audit --skip-editable` | `npm run audit` |
| Unit tests, 85% coverage gate | `uv run pytest -q` | `npm test` (Vitest; markcom-i18n only) |
| Integration tests (own CI job): Linux notifications over a private D-Bus session | `dbus-run-session -- uv run pytest tests/integration --no-cov -q` (markcom only) | none |
| End-to-end | none | `npm run test:e2e` (Playwright; markcom-i18n only) |

Gitleaks and Semgrep run across the whole repository.

## Licence

MIT, see `LICENSE`.
