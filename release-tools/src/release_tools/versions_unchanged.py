"""Pull request check: fails when a pull request changes a library's version. CI writes every
version when it releases, sized by the pull request's labels. Run at GitHub's pull request merge
commit, whose first parent is main."""

from git import Repo

from release_tools.libraries import LIBRARIES, Library, VersionError
from release_tools.report import error, say

MAIN = "HEAD^1"
PULL_REQUEST = "HEAD"


def _check(repo: Repo, library: Library) -> bool:
    try:
        before = library.version_at(repo, MAIN)
        after = library.version_at(repo, PULL_REQUEST)
    except VersionError as failure:
        error(str(failure))
        return False
    if after != before:
        error(
            f"{library.name}: version changed from {before} to {after}; CI sets versions, so "
            "leave the version files alone and label the pull request release:minor or "
            "release:major for a bigger bump than a patch"
        )
        return False
    say(f"{library.name}: {after}, unchanged")
    return True


def main() -> int:
    repo = Repo(search_parent_directories=True)
    results = [_check(repo, library) for library in LIBRARIES]
    return 0 if all(results) else 1
