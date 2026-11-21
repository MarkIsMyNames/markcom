"""Names the release-tools scripts share: git refs, file details and environment variables."""

ENCODING = "utf-8"

REMOTE = "origin"
MAIN = "main"
REMOTE_MAIN = f"{REMOTE}/{MAIN}"
HEAD = "HEAD"
PUSH_HEAD_TO_MAIN = f"{HEAD}:{MAIN}"

VERSION_KEY = "version"

CODE_FOLDER = "src"
PYPROJECT = "pyproject.toml"
UV_LOCK = "uv.lock"
PACKAGE_JSON = "package.json"
PACKAGE_LOCK = "package-lock.json"
PROJECT_TABLE = "project"
# npm's own formatting
NPM_INDENT = 2

# GITHUB_* set by GitHub Actions; the rest by our workflows
LABELS_VARIABLE = "RELEASE_LABELS"
OUTPUT_VARIABLE = "GITHUB_OUTPUT"
