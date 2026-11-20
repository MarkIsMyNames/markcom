"""Names the release scripts share: git refs, the tag format and file details."""

ENCODING = "utf-8"

REMOTE = "origin"
MAIN = "main"
REMOTE_MAIN = f"{REMOTE}/{MAIN}"
# the commit a run is for: the pushed commit, or a pull request's merge commit
HEAD = "HEAD"
PUSH_HEAD_TO_MAIN = f"{HEAD}:{MAIN}"
# a pull request merge commit's first parent: main as the pull request found it
MAIN_BEFORE_MERGE = f"{HEAD}^1"

VERSION_KEY = "version"

# set in GitHub Actions: the event that started the run, and the files a step adds its outputs
# and its Markdown summary to
EVENT_VARIABLE = "GITHUB_EVENT_NAME"
OUTPUT_VARIABLE = "GITHUB_OUTPUT"
SUMMARY_VARIABLE = "GITHUB_STEP_SUMMARY"
# set by the workflows: the repository's default branch
DEFAULT_BRANCH_VARIABLE = "DEFAULT_BRANCH"
PULL_REQUEST_EVENT = "pull_request"
