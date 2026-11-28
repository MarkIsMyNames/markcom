import os
from enum import StrEnum
from pathlib import Path

from git import GitCommandError, Repo
from markcom.config import ConfigError
from markcom.runner import run
from markcom.secrets import NoSecrets
from semver import Version

from release_tools.config import CONFIG_PATH, Labels, ToolConfig
from release_tools.libraries import (
    HEAD,
    MAIN,
    REMOTE,
    REMOTE_MAIN,
    Library,
    VersionError,
    load_libraries,
)
from release_tools.report import error, say, set_output

PUSH_HEAD_TO_MAIN: str = f"{HEAD}:{MAIN}"
# set by release.yml, one label per line
LABELS_VARIABLE: str = "RELEASE_LABELS"
GIT_USER: str = "user"
GIT_NAME: str = "name"
GIT_EMAIL: str = "email"
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


def _publish(repo: Repo, releases: list[tuple[Library, Version]], config: ToolConfig) -> list[str]:
    for library, version in releases:
        library.write_version(Path(repo.working_dir), version)
    # the bot commits and tags; CI's checkout has no git identity of its own
    with repo.config_writer() as git_config:
        git_config.set_value(GIT_USER, GIT_NAME, config.bot.name)
        git_config.set_value(GIT_USER, GIT_EMAIL, config.bot.email)
    # clean: a first release declares the version already
    if repo.is_dirty():
        summary: str = ", ".join(
            f"{library.config.name} {version}" for library, version in releases
        )
        repo.git.commit("-a", "-m", f"{config.release_commit_prefix}{summary}")
    tags: list[str] = [library.tag(version) for library, version in releases]
    for tag in tags:
        repo.create_tag(tag, message=tag)
    # all or nothing: a release commit on main without its tag would block every later run
    repo.git.push("--atomic", REMOTE, PUSH_HEAD_TO_MAIN, *tags)
    return tags


def _release(config: ToolConfig, _secrets: NoSecrets) -> None:
    repo: Repo = Repo(search_parent_directories=True)
    repo.remote(REMOTE).fetch(MAIN)
    # the run for main's newest commit releases it
    if repo.commit(REMOTE_MAIN) != repo.commit(HEAD):
        moved: str = "main has moved past this commit"
        raise ReleaseError(moved)
    level: BumpLevel = _bump_level(os.environ[LABELS_VARIABLE].splitlines(), config.labels)
    releases: list[tuple[Library, Version]] = [
        (library, version)
        for library in load_libraries(Path(repo.working_dir), config.release_config)
        if (version := _next_version(repo, library, level)) is not None
    ]
    if not releases:
        say("nothing to release")
        return
    set_output(TAGS_OUTPUT, TAG_SEPARATOR.join(_publish(repo, releases, config)))
    for library, version in releases:
        say(f"released {library.config.name} {version}")


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
