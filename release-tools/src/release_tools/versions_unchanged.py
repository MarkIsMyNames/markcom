"""Pull request check: fails when a pull request changes a library's version. CI writes every
version when it releases, sized by the pull request's labels. Run at GitHub's pull request merge
commit, whose first parent is main."""

from pathlib import Path

from git import Repo
from markcom import NoSecrets, run
from markcom.config import ConfigError

from release_tools.config import CONFIG_PATH, Labels, ToolConfig
from release_tools.constants import HEAD, MAIN_BEFORE_MERGE
from release_tools.libraries import Library, VersionError, load_libraries
from release_tools.report import error, say


def _check(repo: Repo, library: Library, labels: Labels) -> bool:
    try:
        after = library.version_at(repo, HEAD)
        if not library.exists_at(repo, MAIN_BEFORE_MERGE):
            say(f"{library.name}: {after}, new")
            return True
        before = library.version_at(repo, MAIN_BEFORE_MERGE)
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


def _main(config: ToolConfig, _secrets: NoSecrets) -> int:
    repo = Repo(search_parent_directories=True)
    try:
        libraries = load_libraries(Path(repo.working_dir), config.release_config)
    except ConfigError as failure:
        error(str(failure))
        return 1
    results = [_check(repo, library, config.labels) for library in libraries]
    return 0 if all(results) else 1


def main() -> int:
    return run(_main, CONFIG_PATH, ToolConfig, NoSecrets)
