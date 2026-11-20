"""Names the release scripts share: git refs, the tag format and file details."""

ENCODING = "utf-8"

REMOTE = "origin"
MAIN = "main"
REMOTE_MAIN = f"{REMOTE}/{MAIN}"
# the commit a run is for: the pushed commit, or a pull request's merge commit
HEAD = "HEAD"
PUSH_HEAD_TO_MAIN = f"{HEAD}:{MAIN}"

VERSION_KEY = "version"

# set by GitHub Actions; DEFAULT_BRANCH by our workflows
OUTPUT_VARIABLE = "GITHUB_OUTPUT"
DEFAULT_BRANCH_VARIABLE = "DEFAULT_BRANCH"
