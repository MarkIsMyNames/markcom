import json
from collections.abc import Callable
from pathlib import Path

import pytest
from git import Repo

# release-tools/src/release_tools/conftest.py -> the repository root
ROOT = Path(__file__).resolve().parents[3]


class Clone:
    """A throwaway clone of this repository's HEAD. Its origin is a bare repository holding that
    commit as main and no tags, so tests never depend on the real repository's releases."""

    def __init__(self, tmp_path: Path) -> None:
        self.origin = Repo.init(tmp_path / "origin.git", bare=True, initial_branch="main")
        # no hooks: this push only copies commits out of the real repository
        Repo(ROOT).git(c="core.hooksPath=/dev/null").push(
            self.origin.working_dir, "HEAD:refs/heads/main"
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

    def set_npm_version(self, library: str, version: str, *, lock: bool = False) -> None:
        """Sets package.json's version; with `lock`, package-lock.json's root entries too."""
        self.edit_json(f"{library}/package.json", lambda data: data.update(version=version))
        if lock:

            def set_lock(data):
                data["version"] = version
                data["packages"][""]["version"] = version

            self.edit_json(f"{library}/package-lock.json", set_lock)

    def edit_json(self, relative: str, change: Callable[[dict], object]) -> None:
        path = self.path / relative
        data = json.loads(path.read_text(encoding="utf-8"))
        change(data)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def append(self, relative: str, text: str) -> None:
        with (self.path / relative).open("a", encoding="utf-8") as file:
            file.write(text)

    def write(self, relative: str, text: str) -> None:
        (self.path / relative).write_text(text, encoding="utf-8")

    def push_to_main(self, change: Callable[[], None]) -> None:
        """Commits what `change` does and pushes it to origin's main, as a merged PR lands."""
        change()
        self.repo.git.commit("-a", "--allow-empty", "-m", "change")
        self.repo.git.push("origin", "HEAD:main")

    def tag_off_main(self, tag: str) -> None:
        """Tags a commit that main never holds, as markcom's old off-main release commits."""
        self.repo.git.switch("-c", "off-main")
        self.append("README.md", "\noff main\n")
        self.repo.git.commit("-a", "-m", "off main")
        self.repo.git.tag("-a", tag, "-m", tag)
        self.repo.git.push("origin", tag)
        self.repo.git.switch("main")

    def origin_tags(self) -> set[str]:
        return {tag.name for tag in self.origin.tags}

    def origin_main(self):
        return self.origin.commit("main")

    def tagged_commit(self, tag: str):
        return self.origin.tags[tag].commit

    def file_at_origin_main(self, relative: str) -> str:
        return self.origin.git.show(f"main:{relative}")


@pytest.fixture
def clone(tmp_path, monkeypatch):
    made = Clone(tmp_path)
    monkeypatch.chdir(made.path)
    return made
