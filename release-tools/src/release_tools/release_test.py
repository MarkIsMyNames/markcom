import json
import os
import tomllib
from pathlib import Path

import pytest

from release_tools.release import main

# Expected versions are relative to whatever the clone holds when the test starts.
CODE = "markcom/src/markcom/runner.py"


def declared(clone, library):
    if library == "markcom":
        text = (clone.path / "markcom" / "pyproject.toml").read_text(encoding="utf-8")
        return tomllib.loads(text)["project"]["version"]
    text = (clone.path / library / "package.json").read_text(encoding="utf-8")
    return json.loads(text)["version"]


def bumped(version, level):
    major, minor, patch = (int(part) for part in version.split("."))
    return {
        "patch": f"{major}.{minor}.{patch + 1}",
        "minor": f"{major}.{minor + 1}.0",
        "major": f"{major + 1}.0.0",
    }[level]


def changed_lines(clone, before, after, path):
    diff = clone.origin.git.diff(before, after, "--", path).splitlines()
    return [line for line in diff if line[:1] in "+-" and line[:3] not in ("+++", "---")]


def assert_nothing_released(clone, tags, main_commit):
    assert clone.origin_tags() == tags
    assert clone.origin_main() == main_commit


@pytest.fixture
def labels(monkeypatch):
    monkeypatch.setenv("RELEASE_LABELS", "")


@pytest.fixture
def released(clone, monkeypatch):
    """A clone after a first release run: every library tagged at its declared version."""
    monkeypatch.setenv("RELEASE_LABELS", "")
    assert main() == os.EX_OK
    for library in ("markcom", "markcom-web-config", "markcom-i18n"):
        assert f"{library}-v{declared(clone, library)}" in clone.origin_tags()
    return clone


@pytest.mark.usefixtures("labels")
def test_first_run_tags_untagged_libraries_at_their_declared_versions(clone):
    # this repository's state before its first run: markcom tagged on an off-main commit with
    # the same code, the npm packages never tagged
    clone.tag_off_main(f"markcom-v{declared(clone, 'markcom')}")
    tags, pushed = clone.origin_tags(), clone.origin_main()
    npm = ("markcom-web-config", "markcom-i18n")
    assert main() == os.EX_OK
    assert clone.origin_tags() - tags == {f"{name}-v{declared(clone, name)}" for name in npm}
    assert {clone.tagged_commit(f"{name}-v{declared(clone, name)}") for name in npm} == {pushed}
    assert clone.origin_main() == pushed


def _outside_the_code(clone):
    clone.append("markcom/src/markcom/runner_test.py", "\n# x\n")
    clone.write("markcom/src/markcom/conftest.py", "# shared test fixtures\n")
    clone.append("markcom-i18n/src/vite.test.ts", "// x\n")
    clone.edit_json("markcom-i18n/tsconfig.json", lambda data: data.update(compileOnSave=False))


@pytest.mark.parametrize("change", [lambda _clone: None, _outside_the_code])
def test_releases_nothing_without_a_code_change(released, change):
    released.push_to_main(lambda: change(released))
    tags, pushed = released.origin_tags(), released.origin_main()
    assert main() == os.EX_OK
    assert_nothing_released(released, tags, pushed)


def test_code_change_gets_the_next_patch_in_a_release_commit(released):
    old = declared(released, "markcom")
    new = bumped(old, "patch")
    released.push_to_main(lambda: released.append(CODE, "\n# x\n"))
    pushed = released.origin_main()
    assert main() == os.EX_OK
    release = released.origin_main()
    assert release.parents == (pushed,)
    assert release.message.strip() == f"chore(release): markcom {new}"
    assert released.tagged_commit(f"markcom-v{new}") == release
    assert f'version = "{new}"' in released.file_at_origin_main("markcom/pyproject.toml")
    assert changed_lines(released, pushed, release, "markcom/uv.lock") == [
        f'-version = "{old}"',
        f'+version = "{new}"',
    ]


@pytest.mark.parametrize(
    ("library", "relative", "change"),
    [
        # any manifest change counts, dev-only ones included
        ("markcom-i18n", "package.json", lambda data: data["dependencies"].update(zz="^1.0.0")),
        ("markcom-i18n", "package.json", lambda data: data["overrides"].update(zz="^1.0.0")),
        # projects extend web-config's prettier.json directly, so it is its code
        ("markcom-web-config", "prettier.json", lambda data: data.update(zzRule=True)),
    ],
)
def test_manifest_or_config_change_gets_the_next_patch(released, library, relative, change):
    new = bumped(declared(released, library), "patch")
    released.push_to_main(lambda: released.edit_json(f"{library}/{relative}", change))
    assert main() == os.EX_OK
    assert released.tagged_commit(f"{library}-v{new}") == released.origin_main()


def test_several_libraries_share_one_release_commit(released):
    markcom = bumped(declared(released, "markcom"), "patch")
    old_i18n = declared(released, "markcom-i18n")
    i18n = bumped(old_i18n, "patch")

    def both():
        released.append(CODE, "\n# x\n")
        released.append("markcom-i18n/src/vite.ts", "// x\n")

    released.push_to_main(both)
    pushed = released.origin_main()
    assert main() == os.EX_OK
    release = released.origin_main()
    assert release.parents == (pushed,)
    assert released.tagged_commit(f"markcom-v{markcom}") == release
    assert released.tagged_commit(f"markcom-i18n-v{i18n}") == release
    assert release.message.strip() == f"chore(release): markcom {markcom}, markcom-i18n {i18n}"
    assert changed_lines(released, pushed, release, "markcom-i18n/package-lock.json") == [
        f'-  "version": "{old_i18n}",',
        f'+  "version": "{i18n}",',
        f'-      "version": "{old_i18n}",',
        f'+      "version": "{i18n}",',
    ]


def test_next_version_comes_from_the_tag_not_the_version_file(released):
    new = bumped(declared(released, "markcom-web-config"), "patch")

    def edit_version_and_code():
        released.set_npm_version("markcom-web-config", "99.0.0", lock=True)
        released.append("markcom-web-config/src/eslint.ts", "// x\n")

    released.push_to_main(edit_version_and_code)
    assert main() == os.EX_OK
    assert f"markcom-web-config-v{new}" in released.origin_tags()
    manifest = json.loads(released.file_at_origin_main("markcom-web-config/package.json"))
    assert manifest["version"] == new


def test_run_for_a_commit_main_has_moved_past_fails(released, capsys):
    released.push_to_main(lambda: released.append(CODE, "\n# x\n"))
    run_commit = released.repo.head.commit
    released.push_to_main(lambda: released.append("README.md", "\nx\n"))
    tags, newer = released.origin_tags(), released.origin_main()
    released.repo.git.checkout(run_commit.hexsha)
    assert main() == os.EX_SOFTWARE
    assert "main has moved past this commit" in capsys.readouterr().out
    assert_nothing_released(released, tags, newer)


def test_older_run_after_a_newer_release_fails_without_releasing(released, capsys):
    released.push_to_main(lambda: released.append(CODE, "\n# x\n"))
    older = released.repo.head.commit
    released.push_to_main(lambda: released.append("markcom/src/markcom/logs.py", "\n# x\n"))
    assert main() == os.EX_OK
    tags, newer = released.origin_tags(), released.origin_main()
    released.repo.git.checkout(older.hexsha)
    capsys.readouterr()
    assert main() == os.EX_SOFTWARE
    assert "main has moved past this commit" in capsys.readouterr().out
    assert_nothing_released(released, tags, newer)


@pytest.mark.parametrize(
    ("labels", "level"),
    [("documentation\nrelease:minor", "minor"), ("release:minor\nrelease:major", "major")],
)
def test_merged_pull_request_label_sets_the_bump(released, monkeypatch, labels, level):
    markcom = bumped(declared(released, "markcom"), level)
    i18n = bumped(declared(released, "markcom-i18n"), level)

    def change_two():
        released.append(CODE, "\n# x\n")
        released.append("markcom-i18n/src/vite.ts", "// x\n")

    released.push_to_main(change_two)
    monkeypatch.setenv("RELEASE_LABELS", labels)
    tags = released.origin_tags()
    assert main() == os.EX_OK
    assert released.origin_tags() - tags == {f"markcom-v{markcom}", f"markcom-i18n-v{i18n}"}


@pytest.mark.parametrize(
    "hook",
    [
        "exit 1",
        # tags only: the release commit must not land without its tag
        'while read -r old new ref; do case "$ref" in refs/tags/*) exit 1;; esac; done',
    ],
)
def test_rejected_push_releases_nothing(released, capsys, hook):
    released.push_to_main(lambda: released.append(CODE, "\n# x\n"))
    tags, pushed = released.origin_tags(), released.origin_main()
    script = released.path.parent / "origin.git" / "hooks" / "pre-receive"
    script.write_text(f"#!/bin/sh\n{hook}\n", encoding="utf-8")
    script.chmod(0o755)
    assert main() == os.EX_SOFTWARE
    assert "release failed" in capsys.readouterr().out
    assert_nothing_released(released, tags, pushed)


def test_root_level_project_releases_under_its_own_tag_prefix(root_project):
    repo, origin = root_project
    assert main() == os.EX_OK
    assert {tag.name for tag in origin.tags} == {"v0.1.0"}
    with (Path(repo.working_dir) / "src" / "sample" / "__init__.py").open("a") as file:
        file.write("y = 2\n")
    repo.git.commit("-a", "-m", "code")
    repo.git.push("origin", "HEAD:main")
    assert main() == os.EX_OK
    assert {tag.name for tag in origin.tags} == {"v0.1.0", "v0.1.1"}
    assert 'version = "0.1.1"' in origin.git.show("main:pyproject.toml")
    assert 'version = "0.1.1"' in origin.git.show("main:uv.lock")


def test_released_tags_go_to_github_output(released, github_output):
    github_output.write_text("", encoding="utf-8")
    new = bumped(declared(released, "markcom"), "patch")
    released.push_to_main(lambda: released.append(CODE, "\n# x\n"))
    assert main() == os.EX_OK
    assert github_output.read_text(encoding="utf-8") == f"tags=markcom-v{new}\n"


@pytest.mark.usefixtures("labels")
@pytest.mark.parametrize("config", [None, '{"libraries": [{"name": "x", "kind": "pip"}]}'])
def test_missing_or_invalid_release_config_fails(clone, capsys, config):
    def replace_config():
        if config is None:
            clone.repo.git.rm("-q", "release.json")
        else:
            clone.write("release.json", config)

    clone.push_to_main(replace_config)
    tags = clone.origin_tags()
    assert main() == os.EX_SOFTWARE
    assert "release.json" in capsys.readouterr().out
    assert clone.origin_tags() == tags
