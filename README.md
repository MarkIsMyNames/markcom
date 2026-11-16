# markcom

Shared libraries for my Python and TypeScript projects.

| Folder | Package | For |
|---|---|---|
| `markcom/` | `markcom` (Python, installed from git) | typed `config.json`, secrets from `.env`, logging and the `run()` entry point; with the `desktop` extra, notifications and a tray icon |
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

TypeScript, from npm:

```sh
npm install @markcom/i18n
npm install --save-dev @markcom/web-config
```

## Releasing

CI does both on every push to `main`:

- **markcom**: a version raised by hand in `markcom/pyproject.toml` (a minor or major release) is tagged `markcom-v<version>` as it is. Otherwise, if the source or `pyproject.toml` changed since the last release, CI tags the next patch version. Nothing is committed back to `main`.
- **npm packages**: a version raised by hand in `package.json` is published as it is. Otherwise a changed package is published as the next patch version. CI signs in to npm by trusted publishing (OIDC), set up on each package's npm settings page for this repository and `ci.yml`, so no npm token is stored.

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
