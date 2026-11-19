"""Release on main. A library whose code or install manifest changed since its last release is
released at the next version, first committed to main; one with no release yet is released at the
version its files declare. The bump is the largest that the labels of the pull requests merged
since the library's last release, and changing it, ask for. Run at the pushed commit, with every
tag fetched and RELEASE_PULLS set to the JSON that
`gh pr list --state merged --json mergeCommit,labels` prints."""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import override

from git import GitCommandError, Repo

from release_tools.libraries import LIBRARIES, Library, UnreadableVersionError
from release_tools.report import error, say
from release_tools.versions import InvalidVersionError, Version, bump_level

PULLS_VARIABLE = "RELEASE_PULLS"
PUSHED = "HEAD"
BOT_NAME = "github-actions[bot]"
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"


class ReleaseError(RuntimeError):
    pass


# Each merged pull request's labels, by the commit it was merged as.
type PullLabels = dict[str, frozenset[str]]


def _read_pulls(text: str) -> PullLabels:
    try:
        return {
            pull["mergeCommit"]["oid"]: frozenset(label["name"] for label in pull["labels"])
            for pull in json.loads(text)
            if pull["mergeCommit"] is not None
        }
    except (ValueError, KeyError, TypeError) as failure:
        message = (
            f"{PULLS_VARIABLE} is not the JSON that gh pr list --json mergeCommit,labels prints"
        )
        raise ReleaseError(message) from failure


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


def _labels_since(repo: Repo, library: Library, tag: str, pulls: PullLabels) -> list[str]:
    """Labels of the pull requests merged on main since `tag` that changed the library."""
    merged = repo.git.rev_list("--first-parent", f"{tag}..{PUSHED}").split()
    return [
        label
        for commit in merged
        if commit in pulls and library.release_inputs_changed(repo, f"{commit}^1", commit)
        for label in pulls[commit]
    ]


def _decide(repo: Repo, library: Library, pulls: PullLabels) -> Release | None:
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
    tag = library.tag(latest)
    if library.release_inputs_changed(repo, tag, PUSHED):
        return Release(library, declared.bump(bump_level(_labels_since(repo, library, tag, pulls))))
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
        for release in releases:
            repo.create_tag(release.tag, message=str(release))
        # all or nothing: a release commit on main without its tag would block every later run
        repo.git.push("--atomic", "origin", "HEAD:main", *(release.tag for release in releases))


def _run(repo: Repo, pulls_json: str) -> list[Release] | None:
    """Releases what changed and returns it; None when main moved on past this commit."""
    # first: an older run, or a re-run, compares an old commit with newer tags
    if _main_moved_on(repo):
        return None
    pulls = _read_pulls(pulls_json)
    releases = [
        release for library in LIBRARIES if (release := _decide(repo, library, pulls)) is not None
    ]
    if releases:
        _publish(repo, releases)
    return releases


def main() -> int:
    pulls_json = os.environ.get(PULLS_VARIABLE)
    if pulls_json is None:
        error(f"{PULLS_VARIABLE} is not set; set it to gh pr list's merged pull requests")
        return 1
    try:
        releases = _run(Repo(search_parent_directories=True), pulls_json)
    except (ReleaseError, UnreadableVersionError) as failure:
        error(str(failure))
        return 1
    except GitCommandError as failure:
        error(f"release failed: {failure}")
        return 1
    if releases is None:
        say("main moved on; the run for the newer commit releases this")
    elif not releases:
        say("nothing to release")
    for release in releases or ():
        say(f"released {release}")
    return 0
