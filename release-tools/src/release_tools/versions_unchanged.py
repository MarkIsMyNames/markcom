"""Fails when a branch has changed a library's version: CI sets every version when it releases."""

import os
from pathlib import Path

from git import Repo
from markcom.config import ConfigError
from markcom.runner import run
from markcom.secrets import NoSecrets
from semver import Version

from release_tools.config import CONFIG_PATH, Labels, ToolConfig
from release_tools.libraries import HEAD, REMOTE_MAIN, Library, VersionError, load_libraries
from release_tools.report import error, say


def _check(repo: Repo, library: Library, labels: Labels, base: str) -> bool:
    try:
        after: Version = library.version_at(repo, HEAD)
        if not library.exists_at(repo, base):
            say(f"{library.name}: {after}, new")
            return True
        before: Version = library.version_at(repo, base)
    except VersionError as failure:
        error(str(failure))
        return False
    # as text: semver's != ignores build metadata, so 1.0.0+x would pass as 1.0.0
    if str(after) != str(before):
        error(
            f"{library.name}: version changed from {before} to {after}; "
            f"CI sets it, so label the PR {labels.minor} or {labels.major} instead"
        )
        return False
    say(f"{library.name}: {after}, unchanged")
    return True


def _check_all(config: ToolConfig, _secrets: NoSecrets) -> bool:
    repo: Repo = Repo(search_parent_directories=True)
    # a pull request's merge commit or a branch head alike: where it left main
    base: str = repo.git.merge_base(HEAD, REMOTE_MAIN)
    libraries: tuple[Library, ...] = load_libraries(Path(repo.working_dir), config.release_config)
    # a list, not all() on a generator: every library is reported, not just the first failure
    results: list[bool] = [_check(repo, library, config.labels, base) for library in libraries]
    return all(results)


def main() -> int:
    try:
        unchanged: bool = run(_check_all, CONFIG_PATH, ToolConfig, NoSecrets)
    except ConfigError as failure:
        error(str(failure))
        return os.EX_CONFIG
    return os.EX_OK if unchanged else os.EX_DATAERR
