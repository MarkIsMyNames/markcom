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
NAME_KEY = "name"
# uv.lock's array of packages
UV_LOCK_PACKAGES = "package"
# package-lock.json's packages; the root one sits under the empty path
NPM_LOCK_PACKAGES = "packages"
NPM_ROOT_PACKAGE = ""
# npm's own formatting
NPM_INDENT = 2

# GITHUB_* set by GitHub Actions; the rest by our workflows
LABELS_VARIABLE = "RELEASE_LABELS"
OUTPUT_VARIABLE = "GITHUB_OUTPUT"
# release.yml reads steps.release.outputs.tags, space-separated
TAGS_OUTPUT = "tags"
TAG_SEPARATOR = " "
