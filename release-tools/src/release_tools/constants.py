"""Names the release-tools scripts share: git refs, file details and environment variables."""

import re

ENCODING = "utf-8"

REMOTE = "origin"
MAIN = "main"
REMOTE_MAIN = f"{REMOTE}/{MAIN}"
HEAD = "HEAD"
PUSH_HEAD_TO_MAIN = f"{HEAD}:{MAIN}"
FETCHED = "FETCH_HEAD"
# git -z ends each path with NUL, so any file name comes through as it is.
PATH_END = "\0"

VERSION_KEY = "version"
VERSION_PATTERN = re.compile(r"(\d+)\.(\d+)\.(\d+)")

CODE_FOLDER = "src"
PYPROJECT = "pyproject.toml"
UV_LOCK = "uv.lock"
PACKAGE_JSON = "package.json"
PACKAGE_LOCK = "package-lock.json"
PROJECT_TABLE = "project"
# npm's own formatting
NPM_INDENT = 2

NO_CHANGES = "No changes"

# GITHUB_* set by GitHub Actions; the rest by our workflows
LABELS_VARIABLE = "RELEASE_LABELS"
SNAPSHOTS_VARIABLE = "SNAPSHOTS_DIR"
BRANCH_VARIABLE = "GITHUB_REF_NAME"
OUTPUT_VARIABLE = "GITHUB_OUTPUT"
SUMMARY_VARIABLE = "GITHUB_STEP_SUMMARY"
