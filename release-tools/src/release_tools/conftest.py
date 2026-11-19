import json
from collections.abc import Callable
from pathlib import Path

import pytest
from git import Repo

# release-tools/src/release_tools/conftest.py -> the repository root
ROOT = Path(__file__).resolve().parents[3]


class Clone:
    """A throwaway clone of this repository's HEAD. Its origin is a bare repository holding that
    commit as main, and every tag."""

    def __init__(self, tmp_path: Path) -> None:
        self.origin = Repo.init(tmp_path / "origin.git", bare=True, initial_branch="main")
        # no hooks: this push only copies commits out of the real repository
        Repo(ROOT).git(c="core.hooksPath=/dev/null").push(
            self.origin.working_dir, "HEAD:refs/heads/main", "refs/tags/*:refs/tags/*"
        )
        self.repo = Repo.clone_from(self.origin.working_dir, tmp_path / "work")
        with self.repo.config_writer() as config:
            config.set_value("user", "name", "test")
            config.set_value("user", "email", "test@example.com")
        self.path = Path(self.repo.working_dir)

    def merge_pr(self, change: Callable[[], None]) -> None:
        """Commits what `change` does on a branch from HEAD, then merges it into HEAD with a merge
        commit, as GitHub checks out a pull request: HEAD^1 is main, HEAD the merge."""
        self.repo.git.switch("-c", "pr")
        change()
        self.repo.git.commit("-a", "--allow-empty", "-m", "pr")
        self.repo.git.switch("main")
        self.repo.git.merge("--no-ff", "pr", "-m", "merge")

    def set_markcom_version(self, version: str) -> None:
        pyproject = self.path / "markcom" / "pyproject.toml"
        lines = pyproject.read_text(encoding="utf-8").splitlines(keepends=True)
        pyproject.write_text(
            "".join(
                f'version = "{version}"\n' if line.startswith("version = ") else line
                for line in lines
            ),
            encoding="utf-8",
        )

    def set_npm_version(self, library: str, version: str) -> None:
        manifest = self.path / library / "package.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["version"] = version
        manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def write(self, relative: str, text: str) -> None:
        (self.path / relative).write_text(text, encoding="utf-8")


@pytest.fixture
def clone(tmp_path, monkeypatch):
    made = Clone(tmp_path)
    monkeypatch.chdir(made.path)
    return made
