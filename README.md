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
markcom = { git = "https://github.com/MarkIsMyNames/markcom", subdirectory = "markcom", tag = "markcom-v0.2.3" }
```

TypeScript, from npm:

```sh
npm install @markcom/i18n
npm install --save-dev @markcom/web-config
```

## Releasing

CI does both on every push to `main`:

- **markcom**: raise `version` in `markcom/pyproject.toml`. CI tags it `markcom-v<version>` if that tag is new.
- **npm packages**: a version raised by hand in `package.json` is published as it is. Otherwise a changed package is published as the next patch version. CI signs in to npm by trusted publishing (OIDC), set up on each package's npm settings page for this repository and `ci.yml`, so no npm token is stored.

## Checks

`pre-commit install` runs the same lint, format, type, security, audit and test checks as CI before each commit.

## Licence

MIT, see `LICENSE`.
