# markcom

Shared libraries for the owner's Python and TypeScript projects. Other projects install them by release, so a change here reaches every project on its next release; README.md describes what each library does.

Always reply in caveman mode (the `caveman` skill), from the first reply to the last; `.caveman.json` sets it as this repository's default. Code, commit messages, docs and comments stay in full sentences, as that skill says.

## Layout and checks

`pre-commit run --all-files` runs every check below, the same as CI. Run a folder's own checks from inside it.

| Folder | What | Checks |
|---|---|---|
| `markcom/` | Python library (uv), installed by git tag | `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`, `uv run bandit -q -r src -x '*_test.py'`, `uv run pip-audit --skip-editable`, `uv run pytest -q` |
| `markcom-web-config/` | npm: shared ESLint, Prettier, TypeScript and Vitest settings | `npm run lint`, `npm run format:check`, `npm run typecheck`, `npm run build`, `npm run audit` |
| `markcom-i18n/` | npm: locales, i18next and routing | as web-config, plus `npm test` and `npm run test:e2e`; build web-config first (`npm ci && npm run build` there), as i18n lints with it |
| `release-tools/` | Python (uv): CI's release scripts | as markcom, with `uv run bandit -q -r src -c pyproject.toml` |

- Tests sit beside the code: `*_test.py`, `*.test.ts`. Never suppress a lint, type or scanner finding inline; fix it.
- After changing a `pyproject.toml`'s dependencies, run `uv lock`: CI installs with `--locked`.
- `default.json` (the Renovate preset) and `.github/workflows/security.yml` are used by every one of the owner's repositories, so a change there applies everywhere.
- `docs/` is git-ignored: design specs and plans stay local.

## Releasing

CI releases each library and is the only thing that changes a version; README.md's Releasing section has the full rules.

- Never change a library's version: `version` in `markcom/pyproject.toml`, `markcom/uv.lock`, a `package.json` or a `package-lock.json`. The `versions-unchanged` check fails a pull request that does.
- A change to a library's code or install manifest is released as the next patch. For a minor or major release, ask the owner to label the pull request `release:minor` or `release:major`; below 1.0, a breaking change takes `release:minor`, as `release:major` gives 1.0.0. Tests, lock files, dev dependencies and tool settings release nothing.
- Never run `npm publish`, push a `markcom-*` tag or push a version commit to `main`. `chore(release): …` commits on `main` come from CI; pull before branching.
- Change `release-tools/` test first: its tests run the tools against throwaway clones of this repository.
