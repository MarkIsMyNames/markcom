from pathlib import Path

import pytest
from git import Repo

from release_tools.visual_baselines import commit, restore

SNAPSHOTS = "visual/__snapshots__"


class Project:
    """A throwaway project: origin's main holds baselines a.png and b.png, and the working clone
    is on a pull request branch, feature, pushed to origin."""

    def __init__(self, tmp_path: Path) -> None:
        self.origin = Repo.init(tmp_path / "origin.git", bare=True, initial_branch="main")
        self.repo = Repo.init(tmp_path / "work", initial_branch="main")
        with self.repo.config_writer() as config:
            config.set_value("user", "name", "test")
            config.set_value("user", "email", "test@example.com")
        self.path = Path(self.repo.working_dir)
        self.repo.create_remote("origin", self.origin.working_dir)
        (self.path / "README.md").write_text("project\n", encoding="utf-8")
        self.write_image("a.png", b"a on main")
        self.write_image("b.png", b"b on main")
        self.commit_all("baselines")
        self.repo.git.push("origin", "main")
        self.repo.git.switch("-c", "feature")
        self.repo.git.push("-u", "origin", "feature")

    def write_image(self, name: str, data: bytes) -> None:
        folder = self.path / SNAPSHOTS
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(data)

    def image(self, name: str) -> bytes:
        return (self.path / SNAPSHOTS / name).read_bytes()

    def commit_all(self, message: str) -> None:
        self.repo.git.add("-A")
        self.repo.git.commit("-m", message)

    def origin_feature(self):
        return self.origin.commit("feature")

    def image_at_origin_feature(self, name: str) -> bytes:
        return (self.origin_feature().tree / SNAPSHOTS / name).data_stream.read()


@pytest.fixture
def project(tmp_path, monkeypatch):
    made = Project(tmp_path)
    monkeypatch.chdir(made.path)
    monkeypatch.setenv("SNAPSHOTS_DIR", SNAPSHOTS)
    monkeypatch.setenv("DEFAULT_BRANCH", "main")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    yield made
    made.repo.close()
    made.origin.close()


def summary(tmp_path) -> str:
    return (tmp_path / "summary.md").read_text(encoding="utf-8")


def an_earlier_run_changed_a(project):
    project.write_image("a.png", b"a from an earlier run")
    project.commit_all("test(visual): update baselines")
    project.repo.git.push()


def test_restore_puts_back_the_default_branchs_baselines(project):
    an_earlier_run_changed_a(project)
    assert restore() == 0
    assert project.image("a.png") == b"a on main"
    assert project.image("b.png") == b"b on main"


def test_restore_keeps_a_baseline_new_on_the_branch(project):
    project.write_image("c.png", b"c, a new story")
    project.commit_all("new story")
    assert restore() == 0
    assert project.image("c.png") == b"c, a new story"


def test_restore_changes_nothing_when_the_default_branch_has_no_baselines(project):
    project.repo.git.rm("-r", "-q", SNAPSHOTS)
    project.commit_all("no baselines")
    project.repo.git.push("origin", "HEAD:main", "--force")
    project.write_image("a.png", b"a, first baselines")
    assert restore() == 0
    assert project.image("a.png") == b"a, first baselines"


def test_commit_with_no_image_changed_makes_no_commit(project, tmp_path):
    before = project.origin_feature()
    assert commit() == 0
    assert project.origin_feature() == before
    assert "No changes" in summary(tmp_path)


def test_commit_pushes_only_the_changed_images_and_reports_them(project, tmp_path):
    project.write_image("a.png", b"a changed")
    project.write_image("c.png", b"c added")
    (project.path / "README.md").write_text("an unrelated edit\n", encoding="utf-8")
    assert commit() == 0
    pushed = project.origin_feature()
    assert set(pushed.stats.files) == {f"{SNAPSHOTS}/a.png", f"{SNAPSHOTS}/c.png"}
    report = summary(tmp_path)
    assert pushed.hexsha in report
    assert f"{SNAPSHOTS}/a.png" in report
    assert f"{SNAPSHOTS}/c.png" in report
    assert f"{SNAPSHOTS}/b.png" not in report


def test_a_second_change_is_compared_with_the_default_branch_not_the_earlier_run(project):
    an_earlier_run_changed_a(project)
    restore()
    assert project.image("a.png") == b"a on main"
    # Playwright rewrites only screenshots that differ from the restored baselines
    project.write_image("a.png", b"a changed again")
    assert commit() == 0
    assert project.image_at_origin_feature("a.png") == b"a changed again"


def test_a_story_back_to_the_default_branchs_look_gets_main_s_baseline_back(project, tmp_path):
    an_earlier_run_changed_a(project)
    restore()
    # the screenshot matches main's baseline, so Playwright leaves it as restored
    assert commit() == 0
    assert project.image_at_origin_feature("a.png") == b"a on main"
    assert f"{SNAPSHOTS}/a.png" in summary(tmp_path)


def test_unchanged_images_keep_their_files(project):
    an_earlier_run_changed_a(project)
    restore()
    project.write_image("a.png", b"a changed again")
    commit()
    assert project.image_at_origin_feature("b.png") == b"b on main"
    assert f"{SNAPSHOTS}/b.png" not in project.origin_feature().stats.files
