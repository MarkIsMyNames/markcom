"""The git steps of markcom's visual-baselines workflow, run in a project's checkout of a pull
request branch, with the snapshot folder in SNAPSHOTS_DIR and the default branch's name in
DEFAULT_BRANCH.

visual-baselines-restore puts the default branch's baselines back in the snapshot folder, so
Playwright's update compares each story with them, not with an earlier run's, and rewrites only
the screenshots that differ. A story new on the branch keeps its own baseline, as the default
branch has none.

visual-baselines-commit then commits the images that changed, pushes them to the branch, and
writes the commit and those images to the run's summary, or "No changes". It hands the commit to
later steps as the step output `commit`, empty when nothing changed."""

import os
from collections.abc import Callable
from pathlib import Path

from git import Repo
from markcom import NoSecrets, run
from markcom.config import ConfigError

from release_tools.config import CONFIG_PATH, ToolConfig
from release_tools.constants import ENCODING, HEAD, REMOTE
from release_tools.report import error, say

SNAPSHOTS_VARIABLE = "SNAPSHOTS_DIR"
DEFAULT_BRANCH_VARIABLE = "DEFAULT_BRANCH"
# set in GitHub Actions: the files a step adds its Markdown summary and its outputs to
SUMMARY_VARIABLE = "GITHUB_STEP_SUMMARY"
OUTPUT_VARIABLE = "GITHUB_OUTPUT"
FETCHED = "FETCH_HEAD"
NO_CHANGES = "No changes"
# git diff --name-status's mark for a file the commit adds
ADDED = "A"

type Step = Callable[[ToolConfig, NoSecrets], None]


def _restore(_config: ToolConfig, _secrets: NoSecrets) -> None:
    snapshots = os.environ[SNAPSHOTS_VARIABLE]
    branch = os.environ[DEFAULT_BRANCH_VARIABLE]
    with Repo(search_parent_directories=True) as repo:
        repo.git.fetch("--depth=1", REMOTE, branch)
        try:
            repo.commit(FETCHED).tree.join(snapshots)
        except KeyError:
            say(f"{branch} has no baselines yet, so screenshots are compared with the branch's own")
            return
        repo.git.checkout(FETCHED, "--", snapshots)
    say(f"Baselines from {branch}")


def _commit(config: ToolConfig, _secrets: NoSecrets) -> None:
    snapshots = os.environ[SNAPSHOTS_VARIABLE]
    with Repo(search_parent_directories=True) as repo:
        repo.git.add("--all", "--", snapshots)
        changes = repo.git.diff("--staged", "--name-status", "--", snapshots).splitlines()
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
        # named, as the run's checkout may not track the branch
        repo.git.push(REMOTE, f"{HEAD}:refs/heads/{repo.active_branch.name}")
        pushed = repo.head.commit.hexsha
    _summarise(
        [f"Commit: {pushed}", "", "Changed images:", *(_describe(change) for change in changes)]
    )
    # a push with GITHUB_TOKEN starts no workflows, so the next step starts the checks on it
    with Path(os.environ[OUTPUT_VARIABLE]).open("a", encoding=ENCODING) as output:
        output.write(f"commit={pushed}\n")


def _describe(change: str) -> str:
    """A `git diff --name-status` line as a Markdown list item."""
    mark, path = change.split("\t", 1)
    return f"- {path} ({'added' if mark == ADDED else 'changed'})"


def _summarise(lines: list[str]) -> None:
    text = "".join(f"{line}\n" for line in lines)
    say(text.rstrip("\n"))
    with Path(os.environ[SUMMARY_VARIABLE]).open("a", encoding=ENCODING) as summary:
        summary.write(text)


def _main(step: Step) -> int:
    try:
        run(step, CONFIG_PATH, ToolConfig, NoSecrets)
    except ConfigError as failure:
        error(str(failure))
        return 1
    return 0


def restore() -> int:
    return _main(_restore)


def commit() -> int:
    return _main(_commit)
