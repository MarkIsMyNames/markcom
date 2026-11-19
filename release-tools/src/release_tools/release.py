"""Release on main, run at the pushed commit with every tag fetched; main must not have moved past
it. Each library release.json lists whose code changed since its latest tag gets that tag's next
version, sized by the merged pull request's release:minor or release:major label (RELEASE_LABELS,
one per line), otherwise a patch; the version is committed to main and tagged. A library never
tagged is tagged at the version its files declare."""

import os
from pathlib import Path

from git import GitCommandError, Repo
from markcom import NoSecrets, run
from markcom.config import ConfigError

from release_tools.config import CONFIG_PATH, ToolConfig
from release_tools.constants import ENCODING, HEAD, MAIN, PUSH_HEAD_TO_MAIN, REMOTE, REMOTE_MAIN
from release_tools.libraries import Library, VersionError, load_libraries
from release_tools.report import error, say
from release_tools.versions import BumpLevel, Version, bump_level

LABELS_VARIABLE = "RELEASE_LABELS"
# set in GitHub Actions: the file a step writes its outputs to
OUTPUT_VARIABLE = "GITHUB_OUTPUT"


class ReleaseError(RuntimeError):
    pass


def _next_version(repo: Repo, library: Library, level: BumpLevel) -> Version | None:
    """The version to release the library at, or None when it hasn't changed."""
    latest = library.latest_release(repo)
    if latest is None:
        return library.version_at(repo, HEAD)
    if library.changed(repo, library.tag(latest), HEAD):
        return latest.bump(level)
    return None


def _publish(repo: Repo, releases: list[tuple[Library, Version]], config: ToolConfig) -> None:
    """Commits any version files that changed, tags every release, and pushes it all at once."""
    for library, version in releases:
        library.write_version(Path(repo.working_dir), version)
    with repo.git.custom_environment(
        GIT_AUTHOR_NAME=config.bot.name,
        GIT_AUTHOR_EMAIL=config.bot.email,
        GIT_COMMITTER_NAME=config.bot.name,
        GIT_COMMITTER_EMAIL=config.bot.email,
    ):
        if repo.is_dirty():
            summary = ", ".join(f"{library.name} {version}" for library, version in releases)
            repo.git.commit("-a", "-m", f"{config.release_commit_prefix}{summary}")
        tags = [library.tag(version) for library, version in releases]
        for tag in tags:
            repo.create_tag(tag, message=tag)
        # all or nothing: a release commit on main without its tag would block every later run
        repo.git.push("--atomic", REMOTE, PUSH_HEAD_TO_MAIN, *tags)


def _run(repo: Repo, config: ToolConfig) -> None:
    repo.remote(REMOTE).fetch(MAIN)
    if repo.commit(REMOTE_MAIN) != repo.commit(HEAD):
        message = "main has moved past this commit; the run for main's newest commit releases it"
        raise ReleaseError(message)
    try:
        level = bump_level(os.environ[LABELS_VARIABLE].splitlines(), config.labels)
    except KeyError as missing:
        message = f"{LABELS_VARIABLE} must hold the merged pull request's labels, one per line"
        raise ReleaseError(message) from missing
    releases = []
    for library in load_libraries(Path(repo.working_dir), config.release_config):
        version = _next_version(repo, library, level)
        if version is not None:
            releases.append((library, version))
    if not releases:
        say("nothing to release")
        return
    _publish(repo, releases, config)
    for library, version in releases:
        say(f"released {library.name} {version}")
    _report_tags([library.tag(version) for library, version in releases])


def _report_tags(tags: list[str]) -> None:
    """Hands the tags to later steps and jobs, as the step output `tags`, space-separated."""
    # None: not in GitHub Actions, so no step reads it
    output = os.environ.get(OUTPUT_VARIABLE)
    if output is not None:
        with Path(output).open("a", encoding=ENCODING) as file:
            file.write(f"tags={' '.join(tags)}\n")


def _main(config: ToolConfig, _secrets: NoSecrets) -> int:
    try:
        _run(Repo(search_parent_directories=True), config)
    except (ReleaseError, ConfigError, VersionError, GitCommandError) as failure:
        error(f"release failed: {failure}")
        return 1
    return 0


def main() -> int:
    return run(_main, CONFIG_PATH, ToolConfig, NoSecrets)
