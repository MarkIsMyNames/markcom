"""Release on main, run at the pushed commit with every tag fetched. A library whose code or
install manifest changed since its last tag gets the next version, committed to main and tagged;
one never tagged is tagged at the version its files declare. The bump is the largest that the
labels of the pull requests merged since its last tag, and changing it, ask for. RELEASE_PULLS
holds the JSON that `gh pr list --state merged --json mergeCommit,labels` prints."""

import json
import os
from pathlib import Path

from git import GitCommandError, Repo

from release_tools.libraries import LIBRARIES, Library, VersionError
from release_tools.report import error, say
from release_tools.versions import Version, bump_level

PULLS_VARIABLE = "RELEASE_PULLS"
BOT_NAME = "github-actions[bot]"
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"

type Release = tuple[Library, Version]


class ReleaseError(RuntimeError):
    pass


def _read_pulls(text: str) -> dict[str, frozenset[str]]:
    """Each merged pull request's labels, by the commit it was merged as."""
    try:
        return {
            pull["mergeCommit"]["oid"]: frozenset(label["name"] for label in pull["labels"])
            for pull in json.loads(text)
            if pull["mergeCommit"] is not None
        }
    except (ValueError, KeyError, TypeError) as failure:
        message = f"{PULLS_VARIABLE} must hold the JSON that gh pr list prints"
        raise ReleaseError(message) from failure


def _decide(repo: Repo, library: Library, pulls: dict[str, frozenset[str]]) -> Release | None:
    declared = library.version_at(repo, "HEAD")
    latest = library.latest_release(repo)
    if latest is None:
        return library, declared
    if declared != latest:
        message = f"{library.name}: version {declared} differs from the last release, {latest}"
        raise ReleaseError(message)
    tag = library.tag(latest)
    if not library.release_inputs_changed(repo, tag, "HEAD"):
        return None
    # labels of the pull requests merged since the tag that changed this library
    merged = repo.git.rev_list("--first-parent", f"{tag}..HEAD").split()
    labels = [
        label
        for commit in merged
        if commit in pulls and library.release_inputs_changed(repo, f"{commit}^1", commit)
        for label in pulls[commit]
    ]
    return library, declared.bump(bump_level(labels))


def _publish(repo: Repo, releases: list[Release]) -> None:
    """Commits any version files that changed, tags every release, and pushes it all at once."""
    for library, version in releases:
        library.write_version(Path(repo.working_dir), version)
    with repo.git.custom_environment(
        GIT_AUTHOR_NAME=BOT_NAME,
        GIT_AUTHOR_EMAIL=BOT_EMAIL,
        GIT_COMMITTER_NAME=BOT_NAME,
        GIT_COMMITTER_EMAIL=BOT_EMAIL,
    ):
        if repo.is_dirty():
            summary = ", ".join(f"{library.name} {version}" for library, version in releases)
            repo.git.commit("-a", "-m", f"chore(release): {summary}")
        tags = [library.tag(version) for library, version in releases]
        for tag in tags:
            repo.create_tag(tag, message=tag)
        # all or nothing: a release commit on main without its tag would block every later run
        repo.git.push("--atomic", "origin", "HEAD:main", *tags)


def _run(repo: Repo, pulls_json: str) -> None:
    # first: an older run, or a re-run, would compare an old commit with newer tags
    repo.remotes.origin.fetch("main")
    if repo.commit("origin/main") != repo.commit("HEAD"):
        say("main moved on; the run for the newer commit releases this")
        return
    pulls = _read_pulls(pulls_json)
    releases = [found for library in LIBRARIES if (found := _decide(repo, library, pulls))]
    if not releases:
        say("nothing to release")
        return
    _publish(repo, releases)
    for library, version in releases:
        say(f"released {library.name} {version}")


def main() -> int:
    try:
        _run(Repo(search_parent_directories=True), os.environ.get(PULLS_VARIABLE, ""))
    except (ReleaseError, VersionError, GitCommandError) as failure:
        error(f"release failed: {failure}")
        return 1
    return 0
