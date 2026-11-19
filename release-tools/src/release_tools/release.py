"""Release on main. A library whose code or install manifest changed since its last release is
released at the next version, sized by the merged pull request's labels and first committed to
main; one with no release yet is released at the version its files declare. Run at the pushed
commit, with every tag fetched and RELEASE_LABELS set to the merged pull request's labels, one per
line (empty for none)."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import override

from git import GitCommandError, Repo

from release_tools.libraries import LIBRARIES, Library, UnreadableVersionError
from release_tools.report import error, say
from release_tools.versions import BumpLevel, InvalidVersionError, Version, bump_level

LABELS_VARIABLE = "RELEASE_LABELS"
PUSHED = "HEAD"
BOT_NAME = "github-actions[bot]"
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"


class ReleaseError(RuntimeError):
    pass


@dataclass(frozen=True)
class Release:
    library: Library
    version: Version

    @property
    def tag(self) -> str:
        return self.library.tag(self.version)

    @override
    def __str__(self) -> str:
        return f"{self.library.name} {self.version}"


def _decide(repo: Repo, library: Library, level: BumpLevel) -> Release | None:
    try:
        declared = library.version_at(repo, PUSHED)
    except InvalidVersionError as invalid:
        message = f"{library.name}: version {invalid.text} is not of the form X.Y.Z"
        raise ReleaseError(message) from invalid
    latest = library.latest_release(repo)
    if latest is None:
        return Release(library, declared)
    if declared != latest:
        message = (
            f"{library.name}: version {declared} differs from the last release, {latest}; "
            "only CI changes versions"
        )
        raise ReleaseError(message)
    if library.release_inputs_changed(repo, library.tag(latest), PUSHED):
        return Release(library, declared.bump(level))
    return None


def _main_moved_on(repo: Repo) -> bool:
    repo.remotes.origin.fetch("main")
    return repo.commit("origin/main") != repo.commit(PUSHED)


def _publish(repo: Repo, releases: list[Release]) -> None:
    """Commits any version files that changed to main, then tags every release on main's tip."""
    root = Path(repo.working_dir)
    for release in releases:
        release.library.write_version(root, release.version)
    with repo.git.custom_environment(
        GIT_AUTHOR_NAME=BOT_NAME,
        GIT_AUTHOR_EMAIL=BOT_EMAIL,
        GIT_COMMITTER_NAME=BOT_NAME,
        GIT_COMMITTER_EMAIL=BOT_EMAIL,
    ):
        if repo.is_dirty():
            summary = ", ".join(str(release) for release in releases)
            repo.git.commit("-a", "-m", f"chore(release): {summary}")
            repo.git.push("origin", "HEAD:main")
        for release in releases:
            repo.create_tag(release.tag, message=str(release))
        repo.git.push("origin", *(release.tag for release in releases))


def main() -> int:
    labels = os.environ.get(LABELS_VARIABLE)
    if labels is None:
        error(f"{LABELS_VARIABLE} is not set; set it to the merged pull request's labels")
        return 1
    repo = Repo(search_parent_directories=True)
    level = bump_level(labels.splitlines())
    try:
        releases = [
            release
            for library in LIBRARIES
            if (release := _decide(repo, library, level)) is not None
        ]
    except (ReleaseError, UnreadableVersionError) as failure:
        error(str(failure))
        return 1
    if not releases:
        say("nothing to release")
        return 0
    try:
        if _main_moved_on(repo):
            say("main moved on; the run for the newer commit releases this")
            return 0
        _publish(repo, releases)
    except GitCommandError as failure:
        error(f"release failed: {failure}")
        return 1
    for release in releases:
        say(f"released {release}")
    return 0
