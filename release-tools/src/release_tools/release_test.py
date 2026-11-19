import json
import tomllib

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


def pulls(*merged):
    """RELEASE_PULLS as gh pr list prints it: (merge commit, [label names]) per pull request."""
    return json.dumps(
        [
            {"mergeCommit": {"oid": commit.hexsha}, "labels": [{"name": name} for name in names]}
            for commit, names in merged
        ]
    )


def changed_lines(clone, before, after, path):
    diff = clone.origin.git.diff(before, after, "--", path).splitlines()
    return [line for line in diff if line[:1] in "+-" and line[:3] not in ("+++", "---")]


def assert_nothing_released(clone, tags, main_commit):
    assert clone.origin_tags() == tags
    assert clone.origin_main() == main_commit


@pytest.fixture
def labels(monkeypatch):
    monkeypatch.setenv("RELEASE_PULLS", "[]")


@pytest.fixture
def released(clone, monkeypatch):
    """A clone after a first release run: every library tagged at its declared version."""
    monkeypatch.setenv("RELEASE_PULLS", "[]")
    assert main() == 0
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
    assert main() == 0
    assert clone.origin_tags() - tags == {f"{name}-v{declared(clone, name)}" for name in npm}
    assert {clone.tagged_commit(f"{name}-v{declared(clone, name)}") for name in npm} == {pushed}
    assert clone.origin_main() == pushed


def _outside_the_release_inputs(clone):
    clone.append("markcom/src/markcom/runner_test.py", "\n# x\n")
    clone.append("markcom-i18n/src/vite.test.ts", "// x\n")
    clone.append("markcom/pyproject.toml", "\n[tool.zz]\nsetting = true\n")
    clone.edit_json(
        "markcom-i18n/package.json",
        lambda data: (
            data["devDependencies"].update({"zz-dev": "^1.0.0"}),
            data["overrides"].update({"zz-override": "^1.0.0"}),
        ),
    )
    clone.edit_json("markcom-i18n/tsconfig.json", lambda data: data.update(compileOnSave=False))
    # npm install re-sorts dependencies
    clone.edit_json(
        "markcom-web-config/package.json",
        lambda data: data.update(dependencies=dict(reversed(data["dependencies"].items()))),
    )


@pytest.mark.parametrize("change", [lambda _clone: None, _outside_the_release_inputs])
def test_releases_nothing_without_a_change_to_code_or_install_manifest(released, change):
    released.push_to_main(lambda: change(released))
    tags, pushed = released.origin_tags(), released.origin_main()
    assert main() == 0
    assert_nothing_released(released, tags, pushed)


def test_code_change_gets_the_next_patch_in_a_release_commit(released):
    old = declared(released, "markcom")
    new = bumped(old, "patch")
    released.push_to_main(lambda: released.append(CODE, "\n# x\n"))
    pushed = released.origin_main()
    assert main() == 0
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
        # a runtime dependency is part of the install manifest
        ("markcom-i18n", "package.json", lambda data: data["dependencies"].update(zz="^1.0.0")),
        # projects extend web-config's prettier.json directly, so it is its code
        ("markcom-web-config", "prettier.json", lambda data: data.update(zzRule=True)),
    ],
)
def test_release_input_change_gets_the_next_patch(released, library, relative, change):
    new = bumped(declared(released, library), "patch")
    released.push_to_main(lambda: released.edit_json(f"{library}/{relative}", change))
    assert main() == 0
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
    assert main() == 0
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


def _raise_by_hand(clone):
    clone.set_npm_version("markcom-web-config", "99.0.0", lock=True)


def _lower_with_another_change(clone):
    clone.set_markcom_version("0.0.1")
    clone.append("markcom-i18n/src/vite.ts", "// x\n")


def _pre_release(clone):
    clone.set_npm_version("markcom-web-config", "99.0.0-rc.1")


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (_raise_by_hand, "markcom-web-config: version 99.0.0 differs from the last release"),
        (_lower_with_another_change, "markcom: version 0.0.1 differs from the last release"),
        (_pre_release, "markcom-web-config: version 99.0.0-rc.1 is not of the form X.Y.Z"),
    ],
)
def test_bad_version_fails_before_anything_is_released(released, capsys, change, message):
    released.push_to_main(lambda: change(released))
    tags, pushed = released.origin_tags(), released.origin_main()
    assert main() == 1
    assert message in capsys.readouterr().out
    assert_nothing_released(released, tags, pushed)


@pytest.mark.parametrize("value", ["{ broken", None])
def test_bad_pull_list_fails(clone, monkeypatch, capsys, value):
    if value is None:
        monkeypatch.delenv("RELEASE_PULLS", raising=False)
    else:
        monkeypatch.setenv("RELEASE_PULLS", value)
    tags, pushed = clone.origin_tags(), clone.origin_main()
    assert main() == 1
    assert "RELEASE_PULLS" in capsys.readouterr().out
    assert_nothing_released(clone, tags, pushed)


def test_run_for_a_commit_main_has_moved_past_releases_nothing(released, capsys):
    released.push_to_main(lambda: released.append(CODE, "\n# x\n"))
    run_commit = released.repo.head.commit
    released.push_to_main(lambda: released.append("README.md", "\nx\n"))
    tags, newer = released.origin_tags(), released.origin_main()
    released.repo.git.checkout(run_commit.hexsha)
    assert main() == 0
    assert "main moved on" in capsys.readouterr().out
    assert_nothing_released(released, tags, newer)


def test_older_run_after_a_newer_release_says_main_moved_on(released, capsys):
    released.push_to_main(lambda: released.append(CODE, "\n# x\n"))
    older = released.repo.head.commit
    released.push_to_main(lambda: released.append("markcom/src/markcom/logs.py", "\n# x\n"))
    assert main() == 0
    tags, newer = released.origin_tags(), released.origin_main()
    released.repo.git.checkout(older.hexsha)
    capsys.readouterr()
    assert main() == 0
    assert "main moved on" in capsys.readouterr().out
    assert_nothing_released(released, tags, newer)


@pytest.mark.parametrize(
    ("library", "labels", "level"),
    [
        ("markcom", ["documentation", "release:minor"], "minor"),
        ("markcom-i18n", ["release:minor", "release:major"], "major"),
    ],
)
def test_label_sets_the_bump_for_the_library_changed(released, monkeypatch, library, labels, level):
    new = bumped(declared(released, library), level)
    code = CODE if library == "markcom" else "markcom-i18n/src/vite.ts"
    released.push_to_main(lambda: released.append(code, "\n// x\n"))
    monkeypatch.setenv("RELEASE_PULLS", pulls((released.origin_main(), labels)))
    tags = released.origin_tags()
    assert main() == 0
    assert released.origin_tags() - tags == {f"{library}-v{new}"}


def test_label_of_an_earlier_unreleased_pull_request_still_counts(released, monkeypatch):
    # the labelled pull request's own run found main moved on and stood aside
    new = bumped(declared(released, "markcom"), "major")
    released.push_to_main(lambda: released.append(CODE, "\n# x\n"))
    labelled = released.origin_main()
    released.push_to_main(lambda: released.append("README.md", "\nx\n"))
    monkeypatch.setenv(
        "RELEASE_PULLS", pulls((labelled, ["release:major"]), (released.origin_main(), []))
    )
    assert main() == 0
    assert f"markcom-v{new}" in released.origin_tags()


def test_label_applies_only_to_the_libraries_its_pull_request_changed(released, monkeypatch):
    i18n = bumped(declared(released, "markcom-i18n"), "minor")
    markcom = bumped(declared(released, "markcom"), "patch")
    released.push_to_main(lambda: released.append("markcom-i18n/src/vite.ts", "// x\n"))
    labelled = released.origin_main()
    released.push_to_main(lambda: released.append(CODE, "\n# x\n"))
    monkeypatch.setenv(
        "RELEASE_PULLS", pulls((labelled, ["release:minor"]), (released.origin_main(), []))
    )
    tags = released.origin_tags()
    assert main() == 0
    assert released.origin_tags() - tags == {f"markcom-i18n-v{i18n}", f"markcom-v{markcom}"}


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
    assert main() == 1
    assert "release failed" in capsys.readouterr().out
    assert_nothing_released(released, tags, pushed)
