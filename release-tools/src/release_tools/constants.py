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

# a tag is <library><TAG_SEPARATOR><version>, as markcom-v0.4.1
TAG_SEPARATOR = "-v"

VERSION_KEY = "version"
