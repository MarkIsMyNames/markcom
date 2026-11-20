"""Fails when a branch changes a library's version since it left the default branch
(DEFAULT_BRANCH): CI writes every version when it releases, sized by the pull request's labels.
Run at a pull request's merge commit, or at a branch's head when started by hand."""

import os
from pathlib import Path

from git import Repo
from markcom import NoSecrets, run
from markcom.config import ConfigError

from release_tools.config import CONFIG_PATH, Labels, ToolConfig
from release_tools.constants import DEFAULT_BRANCH_VARIABLE, HEAD, REMOTE
from release_tools.libraries import Library, VersionError, load_libraries
from release_tools.report import error, say


def _base(repo: Repo) -> str:
    # at a merge commit, its first parent; at a branch head, its fork point
    default_branch = f"{REMOTE}/{os.environ[DEFAULT_BRANCH_VARIABLE]}"
    return repo.merge_base(HEAD, default_branch)[0].hexsha


def _check(repo: Repo, library: Library, labels: Labels, base: str) -> bool:
    try:
        after = library.version_at(repo, HEAD)
        if not library.exists_at(repo, base):
            say(f"{library.name}: {after}, new")
            return True
        before = library.version_at(repo, base)
    except VersionError as failure:
        error(str(failure))
        return False
    if after != before:
        error(
            f"{library.name}: version changed from {before} to {after}; CI sets versions, so "
            f"leave the version files alone and label the pull request {labels.minor} or "
            f"{labels.major} for a bigger bump than a patch"
        )
        return False
    say(f"{library.name}: {after}, unchanged")
    return True


def _check_all(config: ToolConfig, _secrets: NoSecrets) -> bool:
    repo = Repo(search_parent_directories=True)
    libraries = load_libraries(Path(repo.working_dir), config.release_config)
    # every library is checked and reported, not just those up to the first failure
    base = _base(repo)
    results = [_check(repo, library, config.labels, base) for library in libraries]
    return all(results)


def main() -> int:
    try:
        unchanged = run(_check_all, CONFIG_PATH, ToolConfig, NoSecrets)
    except ConfigError as failure:
        error(str(failure))
        return 1
    return 0 if unchanged else 1
