"""Pull request check: fails when a library's version in the pull request is lower than on main,
or isn't X.Y.Z. Run at GitHub's pull request merge commit, whose first parent is main."""

import sys

from git import Repo

from release_tools.libraries import LIBRARIES, Library, UnreadableVersionError
from release_tools.versions import InvalidVersionError

MAIN = "HEAD^1"
PULL_REQUEST = "HEAD"


def _fail(message: str) -> bool:
    # GitHub Actions shows a line starting ::error:: as an error on the run
    sys.stdout.write(f"::error::{message}\n")
    return False


def _check(repo: Repo, library: Library) -> bool:
    try:
        before = library.version_at(repo, MAIN)
        after = library.version_at(repo, PULL_REQUEST)
    except UnreadableVersionError:
        return _fail(f"could not read {library.name}'s version")
    except InvalidVersionError as error:
        return _fail(f"{library.name}: version {error.text} is not of the form X.Y.Z")
    if after < before:
        return _fail(f"{library.name}: version {after} is lower than {before} on main")
    change = "unchanged" if after == before else f"raised from {before}"
    sys.stdout.write(f"{library.name}: {after}, {change}\n")
    return True


def main() -> int:
    repo = Repo(search_parent_directories=True)
    results = [_check(repo, library) for library in LIBRARIES]
    return 0 if all(results) else 1
