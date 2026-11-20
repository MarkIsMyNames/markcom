from pathlib import Path

import pytest
from git import Repo

from release_tools.visual_baselines import commit, restore

SNAPSHOTS = "visual/__snapshots__"


class Project:
    """A throwaway project. Origin's main holds baselines a.png and b.png, and its pull request
    branch, feature, starts from main. The run's checkout is as actions/checkout makes it: a
    depth-1 clone of the branch alone, with its commit checked out detached."""

    def __init__(self, tmp_path: Path) -> None:
        self.origin = Repo.init(tmp_path / "origin.git", bare=True, initial_branch="main")
        self.seed = Repo.init(tmp_path / "seed", initial_branch="main")
        self._identify(self.seed)
        self.seed.create_remote("origin", self.origin.working_dir)
        seed_path = Path(self.seed.working_dir)
        (seed_path / "README.md").write_text("project\n", encoding="utf-8")
        (seed_path / SNAPSHOTS).mkdir(parents=True)
        (seed_path / SNAPSHOTS / "a.png").write_bytes(b"a on main")
        (seed_path / SNAPSHOTS / "b.png").write_bytes(b"b on main")
        self.seed.git.add("-A")
        self.seed.git.commit("-m", "baselines")
        self.seed.git.push("origin", "main", "main:feature")
        self.repo = Repo.clone_from(
            f"file://{self.origin.working_dir}",
            tmp_path / "work",
            multi_options=["--depth=1", "--branch=feature", "--single-branch"],
        )
        self._identify(self.repo)
        self.repo.git.checkout("--detach")
        self.path = Path(self.repo.working_dir)

    @staticmethod
    def _identify(repo: Repo) -> None:
        with repo.config_writer() as config:
            config.set_value("user", "name", "test")
            config.set_value("user", "email", "test@example.com")

    def write_image(self, name: str, data: bytes) -> None:
        folder = self.path / SNAPSHOTS
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(data)

    def image(self, name: str) -> bytes:
        return (self.path / SNAPSHOTS / name).read_bytes()

    def commit_and_push(self, message: str) -> None:
        """A commit on the branch, as a person or an earlier run makes it."""
        self.repo.git.add("-A")
        self.repo.git.commit("-m", message)
        self.repo.git.push("origin", "HEAD:refs/heads/feature")

    def origin_feature(self):
        return self.origin.commit("feature")

    def image_at_origin_feature(self, name: str) -> bytes:
        return (self.origin_feature().tree / SNAPSHOTS / name).data_stream.read()

    def close(self) -> None:
        for repo in (self.repo, self.seed, self.origin):
            repo.close()


@pytest.fixture
def project(tmp_path, monkeypatch):
    made = Project(tmp_path)
    monkeypatch.chdir(made.path)
    monkeypatch.setenv("SNAPSHOTS_DIR", SNAPSHOTS)
    monkeypatch.setenv("GITHUB_REF_NAME", "feature")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    (tmp_path / "output").touch()
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "output"))
    yield made
    made.close()


def summary(tmp_path) -> str:
    return (tmp_path / "summary.md").read_text(encoding="utf-8")


def output(tmp_path) -> str:
    return (tmp_path / "output").read_text(encoding="utf-8")


def an_earlier_run_changed_a(project):
    project.write_image("a.png", b"a from an earlier run")
    project.commit_and_push("test(visual): update baselines")


def test_restore_puts_back_the_default_branchs_baselines(project):
    an_earlier_run_changed_a(project)
    assert restore() == 0
    assert project.image("a.png") == b"a on main"
    assert project.image("b.png") == b"b on main"


def test_restore_keeps_a_baseline_new_on_the_branch(project):
    project.write_image("c.png", b"c, a new story")
    project.commit_and_push("new story")
    assert restore() == 0
    assert project.image("c.png") == b"c, a new story"


def test_a_baseline_the_branch_deleted_stays_deleted(project):
    project.repo.git.rm("-q", f"{SNAPSHOTS}/b.png")
    project.commit_and_push("story removed")
    restore()
    assert not (project.path / SNAPSHOTS / "b.png").exists()
    assert commit() == 0
    assert f"{SNAPSHOTS}/b.png" not in project.origin_feature().tree.join(SNAPSHOTS)


def test_restore_changes_nothing_when_the_default_branch_has_no_baselines(project):
    project.seed.git.rm("-r", "-q", SNAPSHOTS)
    project.seed.git.commit("-m", "no baselines")
    project.seed.git.push("origin", "main")
    project.write_image("a.png", b"a, first baselines")
    assert restore() == 0
    assert project.image("a.png") == b"a, first baselines"


def test_commit_with_no_image_changed_makes_no_commit(project, tmp_path):
    before = project.origin_feature()
    assert commit() == 0
    assert project.origin_feature() == before
    assert "No changes" in summary(tmp_path)
    assert output(tmp_path) == ""


def test_commit_pushes_only_the_changed_images_and_reports_them(project, tmp_path):
    project.write_image("a.png", b"a changed")
    project.write_image("c.png", b"c added")
    (project.path / "README.md").write_text("an unrelated edit\n", encoding="utf-8")
    assert commit() == 0
    pushed = project.origin_feature()
    assert set(pushed.stats.files) == {f"{SNAPSHOTS}/a.png", f"{SNAPSHOTS}/c.png"}
    assert pushed.author.email == "41898282+github-actions[bot]@users.noreply.github.com"
    report = summary(tmp_path)
    assert pushed.hexsha in report
    assert f"{SNAPSHOTS}/a.png" in report
    assert f"{SNAPSHOTS}/c.png" in report
    assert f"{SNAPSHOTS}/b.png" not in report


def test_an_image_name_is_reported_as_it_is(project, tmp_path):
    project.write_image("Fáilte, a story.png", b"new")
    commit()
    assert f"{SNAPSHOTS}/Fáilte, a story.png" in summary(tmp_path)


def test_the_commit_goes_to_later_steps_so_they_can_start_the_checks(project, tmp_path):
    project.write_image("a.png", b"a changed")
    commit()
    assert output(tmp_path) == f"commit={project.origin_feature().hexsha}\n"


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


def test_a_push_after_the_branch_moved_fails(project, capsys):
    project.seed.git.fetch("origin", "feature")
    project.seed.git.switch("-c", "feature", "origin/feature")
    project.seed.git.commit("--allow-empty", "-m", "pushed during the run")
    project.seed.git.push("origin", "feature")
    project.write_image("a.png", b"a changed")
    assert commit() == 1
    assert "::error::" in capsys.readouterr().out


@pytest.mark.usefixtures("project")
def test_a_missing_snapshot_folder_setting_fails_at_once(monkeypatch):
    monkeypatch.delenv("SNAPSHOTS_DIR")
    with pytest.raises(KeyError):
        commit()
