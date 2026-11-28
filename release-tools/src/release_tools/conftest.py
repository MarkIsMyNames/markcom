import json
from collections.abc import Callable
from pathlib import Path

import pytest
from git import Repo

ROOT = Path(__file__).resolve().parents[3]

MARKCOM_LIBRARIES = {
    "libraries": [
        {
            "name": "markcom",
            "kind": "uv",
            "path": "markcom",
            "tag_prefix": "markcom-v",
            "extra_code": [],
        },
        {
            "name": "markcom-web-config",
            "kind": "npm",
            "path": "markcom-web-config",
            "tag_prefix": "markcom-web-config-v",
            "extra_code": ["tsconfig.json", "prettier.json"],
        },
        {
            "name": "markcom-i18n",
            "kind": "npm",
            "path": "markcom-i18n",
            "tag_prefix": "markcom-i18n-v",
            "extra_code": [],
        },
    ]
}


class Clone:
    """Origin holds HEAD as main, no tags: tests never depend on real releases."""

    def __init__(self, tmp_path: Path) -> None:
        self.origin = Repo.init(tmp_path / "origin.git", bare=True, initial_branch="main")
        # No hooks: push only copies commits from real repository.
        Repo(ROOT).git(c="core.hooksPath=/dev/null").push(
            self.origin.working_dir, "HEAD:refs/heads/main"
        )
        self.repo = Repo.clone_from(self.origin.working_dir, tmp_path / "work")
        with self.repo.config_writer() as config:
            config.set_value("user", "name", "test")
            config.set_value("user", "email", "test@example.com")
        self.path = Path(self.repo.working_dir)
        # Tests' own library list: never depend on repository's release.json.
        self.write("release.json", json.dumps(MARKCOM_LIBRARIES, indent=2) + "\n")
        self.repo.git.add("release.json")
        self.repo.git.commit("-m", "release config")
        self.repo.git.push("origin", "HEAD:main")

    def merge_pr(self, change: Callable[[], None]) -> None:
        """Merge commit as GitHub checks out a PR: HEAD^1 is main, HEAD the merge."""
        self.repo.git.switch("-c", "pr")
        change()
        self.repo.git.add("-A")
        self.repo.git.commit("--allow-empty", "-m", "pr")
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
        change()
        self.repo.git.add("-A")
        self.repo.git.commit("--allow-empty", "-m", "change")
        self.repo.git.push("origin", "HEAD:main")

    def tag_off_main(self, tag: str) -> None:
        """Mimics markcom's old off-main release commits."""
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


@pytest.fixture(autouse=True)
def github_output(tmp_path, monkeypatch):
    """Release appends step outputs here."""
    output = tmp_path / "github-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    return output


@pytest.fixture
def clone(tmp_path, monkeypatch):
    made = Clone(tmp_path)
    monkeypatch.chdir(made.path)
    return made


UV_LOCK = """version = 1
revision = 3
requires-python = ">=3.13"

[[package]]
name = "sample"
version = "0.1.0"
source = { editable = "." }
"""


@pytest.fixture
def root_project(tmp_path, monkeypatch):
    origin = Repo.init(tmp_path / "origin.git", bare=True, initial_branch="main")
    repo = Repo.init(tmp_path / "work", initial_branch="main")
    with repo.config_writer() as config:
        config.set_value("user", "name", "test")
        config.set_value("user", "email", "test@example.com")
    path = Path(repo.working_dir)
    (path / "src" / "sample").mkdir(parents=True)
    (path / "src" / "sample" / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    (path / "pyproject.toml").write_text(
        '[project]\nname = "sample"\nversion = "0.1.0"\nrequires-python = ">=3.13"\n',
        encoding="utf-8",
    )
    (path / "uv.lock").write_text(UV_LOCK, encoding="utf-8")
    library = {"name": "sample", "kind": "uv", "path": ".", "tag_prefix": "v", "extra_code": []}
    (path / "release.json").write_text(json.dumps({"libraries": [library]}), encoding="utf-8")
    repo.git.add("-A")
    repo.git.commit("-m", "init")
    repo.create_remote("origin", origin.working_dir)
    repo.git.push("origin", "HEAD:main")
    monkeypatch.chdir(path)
    monkeypatch.setenv("RELEASE_LABELS", "")
    return repo, origin
