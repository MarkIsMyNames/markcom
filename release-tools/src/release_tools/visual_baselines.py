"""The git steps of markcom's visual-baselines workflow, run in a project's checkout of a pull
request branch's commit, with the snapshot folder in SNAPSHOTS_DIR.

visual-baselines-restore puts the default branch's (DEFAULT_BRANCH) baselines back in the snapshot
folder, so Playwright's update compares each story with them, not with an earlier run's, and
rewrites only the screenshots that differ. A baseline new on the branch keeps its own version, as
the default branch has none, and one the branch deleted stays deleted.

visual-baselines-commit then commits the images that changed, pushes them to the branch
(GITHUB_REF_NAME), and writes the commit and those images to the run's summary, or "No changes".
It hands the commit to later steps as the step output `commit`, empty when nothing changed."""

import os
from collections.abc import Callable
from itertools import batched
from pathlib import Path, PurePosixPath

from git import GitCommandError, Repo
from markcom import NoSecrets, run

from release_tools.config import CONFIG_PATH, ToolConfig
from release_tools.constants import (
    DEFAULT_BRANCH_VARIABLE,
    ENCODING,
    HEAD,
    OUTPUT_VARIABLE,
    REMOTE,
    SUMMARY_VARIABLE,
)
from release_tools.report import error, say

SNAPSHOTS_VARIABLE = "SNAPSHOTS_DIR"
# set in GitHub Actions: the branch the run was started on
BRANCH_VARIABLE = "GITHUB_REF_NAME"
FETCHED = "FETCH_HEAD"
NO_CHANGES = "No changes"
# git's -z output separates its fields with NUL
FIELD_END = "\0"
# git diff --name-status's mark for a file the commit adds
ADDED = "A"

type Step = Callable[[ToolConfig, NoSecrets], None]


def _snapshots() -> str:
    # as git names it: no ./ in front, no / after
    return PurePosixPath(os.environ[SNAPSHOTS_VARIABLE]).as_posix()


def _files(repo: Repo, revision: str, folder: str) -> set[str]:
    listing: str = repo.git.ls_tree("-r", "-z", "--name-only", revision, "--", folder)
    return {path for path in listing.split(FIELD_END) if path}


def _restore(_config: ToolConfig, _secrets: NoSecrets) -> None:
    snapshots = _snapshots()
    branch = os.environ[DEFAULT_BRANCH_VARIABLE]
    with Repo(search_parent_directories=True) as repo:
        repo.git.fetch("--depth=1", REMOTE, branch)
        on_default = _files(repo, FETCHED, snapshots)
        if not on_default:
            say(f"{branch} has no baselines yet, so screenshots are compared with the branch's own")
            return
        # only baselines the branch still has: one it deleted or renamed stays gone
        restored = sorted(on_default & _files(repo, HEAD, snapshots))
        if restored:
            repo.git.checkout(FETCHED, "--", *restored)
    say(f"{len(restored)} baselines from {branch}")


def _commit(config: ToolConfig, _secrets: NoSecrets) -> None:
    snapshots = _snapshots()
    branch = os.environ[BRANCH_VARIABLE]
    with Repo(search_parent_directories=True) as repo:
        repo.git.add("--all", "--", snapshots)
        listing: str = repo.git.diff(
            "--staged", "--name-status", "-z", "--no-renames", "--", snapshots
        )
        fields = [field for field in listing.split(FIELD_END) if field]
        changes = list(batched(fields, 2, strict=True))
        if not changes:
            _summarise([NO_CHANGES])
            return
        with repo.git.custom_environment(
            GIT_AUTHOR_NAME=config.bot.name,
            GIT_AUTHOR_EMAIL=config.bot.email,
            GIT_COMMITTER_NAME=config.bot.name,
            GIT_COMMITTER_EMAIL=config.bot.email,
        ):
            # the snapshot folder only, whatever else the run left changed
            repo.git.commit("-m", config.baselines_commit_message, "--", snapshots)
        # onto the commit the screenshots were made from: rejected if the branch has moved since
        repo.git.push(REMOTE, f"{HEAD}:refs/heads/{branch}")
        pushed = repo.head.commit.hexsha
    _summarise(
        [
            f"Commit: {pushed}",
            "",
            "Changed images:",
            *(f"- {path} ({'added' if mark == ADDED else 'changed'})" for mark, path in changes),
        ]
    )
    # a push with GITHUB_TOKEN starts no workflows, so the next step starts the checks on it
    with Path(os.environ[OUTPUT_VARIABLE]).open("a", encoding=ENCODING) as output:
        output.write(f"commit={pushed}\n")


def _summarise(lines: list[str]) -> None:
    text = "".join(f"{line}\n" for line in lines)
    say(text.rstrip("\n"))
    with Path(os.environ[SUMMARY_VARIABLE]).open("a", encoding=ENCODING) as summary:
        summary.write(text)


def _main(step: Step) -> int:
    try:
        run(step, CONFIG_PATH, ToolConfig, NoSecrets)
    except GitCommandError as failure:
        error(str(failure))
        return 1
    return 0


def restore() -> int:
    return _main(_restore)


def commit() -> int:
    return _main(_commit)
