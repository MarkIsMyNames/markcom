import os
from enum import StrEnum
from pathlib import Path

from git import GitCommandError, Repo
from markcom.config import ConfigError, load_config
from markcom.runner import run
from markcom.secrets import NoSecrets
from semver import Version

from release_tools.config import CONFIG_PATH, Labels, ReleaseConfig, ToolConfig
from release_tools.libraries import (
    ENCODING,
    HEAD,
    MAIN,
    REMOTE,
    REMOTE_MAIN,
    Library,
    VersionError,
    libraries_in,
)
from release_tools.report import error, say

PUSH_HEAD_TO_MAIN: str = f"{HEAD}:{MAIN}"
# set by release.yml, one label per line
LABELS_VARIABLE: str = "RELEASE_LABELS"
OUTPUT_VARIABLE: str = "GITHUB_OUTPUT"
# release.yml reads steps.release.outputs.tags
TAGS_OUTPUT: str = "tags"
TAG_SEPARATOR: str = " "


class ReleaseError(RuntimeError): ...


class BumpLevel(StrEnum):
    # values are semver's next_version part names
    PATCH = "patch"
    MINOR = "minor"
    MAJOR = "major"


def _bump_level(names: list[str], labels: Labels) -> BumpLevel:
    if labels.major in names:
        return BumpLevel.MAJOR
    if labels.minor in names:
        return BumpLevel.MINOR
    return BumpLevel.PATCH


def _next_version(repo: Repo, library: Library, level: BumpLevel) -> Version | None:
    latest: Version | None = library.latest_release(repo)
    # None: never released, so its declared version is its first
    if latest is None:
        return library.version_at(repo, HEAD)
    if library.changed(repo, library.tag(latest), HEAD):
        return latest.next_version(level)
    return None


def _publish(repo: Repo, releases: list[tuple[Library, Version]], config: ToolConfig) -> None:
    for library, version in releases:
        library.write_version(Path(repo.working_dir), version)
    with repo.git.custom_environment(
        GIT_AUTHOR_NAME=config.bot.name,
        GIT_AUTHOR_EMAIL=config.bot.email,
        GIT_COMMITTER_NAME=config.bot.name,
        GIT_COMMITTER_EMAIL=config.bot.email,
    ):
        # clean: a first release declares the version already
        if repo.is_dirty():
            summary: str = ", ".join(f"{library.name} {version}" for library, version in releases)
            repo.git.commit("-a", "-m", f"{config.release_commit_prefix}{summary}")
        tags: list[str] = [library.tag(version) for library, version in releases]
        for tag in tags:
            repo.create_tag(tag, message=tag)
        # all or nothing: a release commit on main without its tag would block every later run
        repo.git.push("--atomic", REMOTE, PUSH_HEAD_TO_MAIN, *tags)
    with Path(os.environ[OUTPUT_VARIABLE]).open("a", encoding=ENCODING) as output:
        output.write(f"{TAGS_OUTPUT}={TAG_SEPARATOR.join(tags)}\n")


def _release(config: ToolConfig, _secrets: NoSecrets) -> None:
    repo: Repo = Repo(search_parent_directories=True)
    repo.remote(REMOTE).fetch(MAIN)
    # the run for main's newest commit releases it
    if repo.commit(REMOTE_MAIN) != repo.commit(HEAD):
        moved: str = "main has moved past this commit"
        raise ReleaseError(moved)
    level: BumpLevel = _bump_level(os.environ[LABELS_VARIABLE].splitlines(), config.labels)
    release: ReleaseConfig = load_config(
        Path(repo.working_dir) / config.release_config, ReleaseConfig
    )
    releases: list[tuple[Library, Version]] = [
        (library, version)
        for library in libraries_in(release)
        if (version := _next_version(repo, library, level)) is not None
    ]
    if not releases:
        say("nothing to release")
        return
    _publish(repo, releases, config)
    for library, version in releases:
        say(f"released {library.name} {version}")


def main() -> int:
    try:
        run(_release, CONFIG_PATH, ToolConfig, NoSecrets)
    except ConfigError as failure:
        error(f"release failed: {failure}")
        return os.EX_CONFIG
    except (ReleaseError, VersionError, GitCommandError) as failure:
        error(f"release failed: {failure}")
        return os.EX_SOFTWARE
    return os.EX_OK
