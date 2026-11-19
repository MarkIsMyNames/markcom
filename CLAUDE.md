# markcom

## Releasing

CI releases the libraries (`markcom`, `@markcom/web-config`, `@markcom/i18n`); README.md's Releasing section has the rules.

- Never change a library's version: `version` in `markcom/pyproject.toml`, `markcom/uv.lock`, a `package.json` or a `package-lock.json`. CI writes every version, and the `versions-unchanged` check fails a pull request that changes one.
- A change to a library's code or install manifest is released as the next patch. For a minor or major release, ask the user to label the pull request `release:minor` or `release:major`; in 0.x, a breaking change takes `release:minor`.
- Never run `npm publish`, push a `markcom-*` tag, or push a version commit to `main`. `chore(release): …` commits on `main` come from CI.
- The release logic is in `release-tools/`, a uv project with its own checks; change it test first.
