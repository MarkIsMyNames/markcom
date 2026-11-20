"""markcom's visual-baselines workflow's git steps, in a checkout of a pull request branch's commit.
visual-baselines-restore puts the default branch's baselines back, so Playwright compares each
story with them; visual-baselines-commit commits and pushes the images that changed."""

import os
from collections.abc import Callable
from pathlib import Path

from git import GitCommandError, Repo
from markcom import NoSecrets, run

from release_tools.config import CONFIG_PATH, ToolConfig
from release_tools.constants import (
    BRANCH_VARIABLE,
    DEFAULT_BRANCH_VARIABLE,
    ENCODING,
    FETCHED,
    HEAD,
    NO_CHANGES,
    OUTPUT_VARIABLE,
    PATH_END,
    REMOTE,
    SNAPSHOTS_VARIABLE,
    SUMMARY_VARIABLE,
)
from release_tools.report import error, say

type Step = Callable[[ToolConfig, NoSecrets], None]


def _paths(listing: str) -> list[str]:
    return [path for path in listing.split(PATH_END) if path]


def _files(repo: Repo, revision: str, folder: str) -> set[str]:
    return set(_paths(repo.git.ls_tree("-r", "-z", "--name-only", revision, "--", folder)))


def _restore(_config: ToolConfig, _secrets: NoSecrets) -> None:
    snapshots = os.environ[SNAPSHOTS_VARIABLE]
    branch = os.environ[DEFAULT_BRANCH_VARIABLE]
    with Repo(search_parent_directories=True) as repo:
        repo.git.fetch("--depth=1", REMOTE, branch)
        # baseline branch deleted or renamed stays gone
        restored = sorted(_files(repo, FETCHED, snapshots) & _files(repo, HEAD, snapshots))
        if restored:
            repo.git.checkout(FETCHED, "--", *restored)
    say(f"{len(restored)} baselines from {branch}")


def _commit(config: ToolConfig, _secrets: NoSecrets) -> None:
    snapshots = os.environ[SNAPSHOTS_VARIABLE]
    with Repo(search_parent_directories=True) as repo:
        repo.git.add("--all", "--", snapshots)
        changed = _paths(repo.git.diff("--staged", "--name-only", "-z", "--", snapshots))
        if not changed:
            _summarise([NO_CHANGES])
            return
        with repo.git.custom_environment(
            GIT_AUTHOR_NAME=config.bot.name,
            GIT_AUTHOR_EMAIL=config.bot.email,
            GIT_COMMITTER_NAME=config.bot.name,
            GIT_COMMITTER_EMAIL=config.bot.email,
        ):
            repo.git.commit("-m", config.baselines_commit_message)
        # onto screenshots' commit: rejected if branch moved since
        repo.git.push(REMOTE, f"{HEAD}:refs/heads/{os.environ[BRANCH_VARIABLE]}")
        pushed = repo.head.commit.hexsha
    _summarise([f"Commit: {pushed}", "", "Changed images:", *(f"- {path}" for path in changed)])
    # GITHUB_TOKEN push starts no workflows; next step starts checks on this commit
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
