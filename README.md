# markcom

Shared code for my projects: `markcom` for Python, `@markcom/i18n` and `@markcom/web-config` for npm, plus the release tool and CI workflows my other repositories call.

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

Import from each module, such as `from markcom.runner import run`. The package imports nothing, so the window process starts without pydantic.

| Module | Function or class | Extra | What it does | Example |
|---|---|---|---|---|
| `markcom.runner` | `run` | none | Loads `config.json` and secrets, sets up logging, then calls `main(config, secrets)`. A config error goes to stderr and exits with `os.EX_CONFIG`. | `run(main, Path("config.json"), AppConfig, AppSecrets)` |
| `markcom.logs` | `configure_logging` | none | Sets the log level and markcom's log format, replacing any earlier set-up. `run` calls it. | `configure_logging("INFO")` |
| `markcom.config` | `BaseAppConfig` | none | Base for an app's `config.json` model, with `log_level`. Every field is required, unknown keys are rejected, and the model is immutable. | `class AppConfig(BaseAppConfig): poll_sec: int` |
| `markcom.secrets` | `BaseSecrets`, `NoSecrets` | none | Base for secrets. Each field comes from its upper-case variable: the environment first, then the `.env` beside `config.json`. `NoSecrets` reads none and ignores `.env`. | `class AppSecrets(BaseSecrets): api_token: SecretStr` |
| `markcom.commands` | `CommandRunner`, `SubprocessRunner`, `BackgroundProcess` | none | Runs programs from argument lists, never through a shell. Starts only the programs it was built with (else `PermissionError`), finds them on its given environment's `PATH`, and passes the child only that environment. `run` returns the `CompletedProcess` with stdout and stderr and never raises on a non-zero exit; call `check_returncode()` for that. `run_in_background` runs a program for a `with` block, then terminates it, killing it after `stop_timeout`. | `SubprocessRunner(frozenset({"npm"}), {"PATH": os.environ["PATH"]}).run(["npm", "ci"])` |
| `markcom.notifier` | `FreedesktopNotifier`, `Notifier`, `Urgency` | `desktop` | Sends Linux desktop notifications over D-Bus from any thread. `send` returns at once; a failed send is logged, never raised. Give it the app's `.desktop` file ID so KDE Plasma keeps expired notifications in its history. | `FreedesktopNotifier("App", icon, "org.example.App")` |
| `markcom.tray` | `Tray`, `TrayAction`, `TrayNotifications` | `window` | Tray icon. Left click opens or closes its target; right click shows its actions and Quit. While entered, ERROR log records become notifications for `error_display_sec`, CRITICAL ones stay until dismissed, and each adds to the badge. | `with Tray(app, icon, TrayNotifications(notifier, 8), window, [TrayAction("Sync", sync)]): app.exec()` |
| `markcom.window` | `WebWindow` | `window` | Shows a web frontend in its own QtWebEngine window, as the tray's target. Each open starts a new process and shows the window once the page loads or fails; each close ends it, freeing its memory. Keeps size and maximised state in `~/.config/markcom/<title>.conf`; keeps no cookies or site storage; downloads nothing. The extra pulls in Qt and WebEngine, about 260 MB on Linux. | `WebWindow("App", url, icon)` |
| `markcom.own_origin` | `OwnOriginOnly` | `web` | ASGI middleware for a loopback server. Refuses any request or websocket whose Host, or Origin if present, isn't the server's own address and port. This stops DNS rebinding and cross-origin websockets. | `OwnOriginOnly(app, IPv4Address("127.0.0.1"), 8080)` |
| `markcom.ui_server` | `UiServer` | `nicegui` | Serves a NiceGUI UI behind `OwnOriginOnly` on its own thread, leaving the main thread to the tray and window. | `with UiServer(root, "App", IPv4Address("127.0.0.1"), 8080): app.exec()` |
| `markcom.page_refresh` | `keep_current`, `announce` | `nicegui` | `keep_current` draws a page's body and redraws it when an announced change alters what it shows. `announce` is safe from any thread. | `refresh = keep_current(read, body, changed)` |

### @markcom/i18n

| Import | What it does |
|---|---|
| `@markcom/i18n` | Locale lookup and browser-language detection (`LocaleSet`, `lookupString`) |
| `@markcom/i18n/i18next` | i18next set-up (`createI18n`) |
| `@markcom/i18n/vite` | The `index.html` locale plugin, which also checks every locale file at build time (`localeHtmlPlugin`) |
| `@markcom/i18n/react-router` | `/<lang>/` routing (`languageRoutes`) |
| `@markcom/i18n/vitest-setup` | A Vitest setup file in which `t()` returns each key unchanged |

### @markcom/web-config

| Import | What it does |
|---|---|
| `@markcom/web-config/eslint` | ESLint settings (`createEslintConfig`) |
| `@markcom/web-config/prettier` | Prettier settings |
| `@markcom/web-config/tsconfig.json` | TypeScript settings to extend |
| `@markcom/web-config/vitest` | Vitest coverage settings (`coverageGate`) |
| `@markcom/web-config/playwright` | Playwright settings (`createPlaywrightConfig`) |
| `@markcom/web-config/story-screenshots` | The test that screenshots every Storybook story (`testStoryScreenshots`) |
| `@markcom/web-config/storybook` | Storybook settings (`createStorybookConfig`) |

## Commands

Run the `uv` commands in `markcom/` and `release-tools/`, and the `npm` commands in `markcom-i18n/` and `markcom-web-config/`.

| Command | What it does |
|---|---|
| `pre-commit install` | Runs every check below, plus Gitleaks and Semgrep, before each commit |
| `pre-commit run --all-files` | Runs every check now, as CI does |
| `uv run pytest -q` | Unit tests with an 85% coverage gate (pytest) |
| `dbus-run-session -- uv run pytest e2e --no-cov -q` | Notification end-to-end tests on a private D-Bus session (pytest; markcom only) |
| `uv run ruff check .` | Lint (Ruff) |
| `uv run ruff format --check .` | Format check (Ruff) |
| `uv run mypy src` | Type check (mypy) |
| `uv run bandit -q -r src -c pyproject.toml` | Security scan (Bandit) |
| `uv lock --check` | Checks that `uv.lock` matches `pyproject.toml` |
| `uv run pip-audit --skip-editable` | Dependency audit (pip-audit) |
| `npm test` | Unit tests with an 85% coverage gate (Vitest) |
| `npm run test:e2e` | Routing end-to-end tests on a small test site (Playwright; markcom-i18n only) |
| `npm run lint` | Lint, with security rules (ESLint) |
| `npm run format:check` | Format check (Prettier) |
| `npm run typecheck` | Type check (tsc) |
| `npm run audit` | Dependency audit (npm audit) |
