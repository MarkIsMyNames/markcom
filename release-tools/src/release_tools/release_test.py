import json
import tomllib

import pytest

from release_tools.release import main

# Expected versions are relative to whatever the clone holds when the test starts.


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


@pytest.fixture
def labels(monkeypatch):
    monkeypatch.setenv("RELEASE_LABELS", "")


@pytest.fixture
def released(clone, monkeypatch):
    """A clone after a first release run: every library tagged at its declared version."""
    monkeypatch.setenv("RELEASE_LABELS", "")
    assert main() == 0
    for library in ("markcom", "markcom-web-config", "markcom-i18n"):
        assert f"{library}-v{declared(clone, library)}" in clone.origin_tags()
    return clone


@pytest.mark.usefixtures("labels")
def test_first_run_tags_untagged_libraries_at_their_declared_versions(clone):
    pushed = clone.origin_main()
    assert main() == 0
    for library in ("markcom-web-config", "markcom-i18n"):
        assert clone.tagged_commit(f"{library}-v{declared(clone, library)}") == pushed
    assert clone.origin_main() == pushed


def test_nothing_changed_releases_nothing(released):
    tags, pushed = released.origin_tags(), released.origin_main()
    assert main() == 0
    assert released.origin_tags() == tags
    assert released.origin_main() == pushed


def test_changes_outside_the_release_inputs_release_nothing(released):
    def outside():
        released.append("markcom/src/markcom/runner_test.py", "\n# x\n")
        released.append("markcom-i18n/src/vite.test.ts", "// x\n")
        released.edit_json(
            "markcom-i18n/package.json",
            lambda data: (
                data["devDependencies"].update({"zz-dev": "^1.0.0"}),
                data["overrides"].update({"zz-override": "^1.0.0"}),
            ),
        )
        released.replace("markcom/pyproject.toml", "dev = [\n", 'dev = [\n    "zz-dev>=1",\n')
        released.replace("markcom/pyproject.toml", "[tool.ruff]\n", "[tool.ruff]\nfix = false\n")
        released.edit_json(
            "markcom-i18n/tsconfig.json", lambda data: data.update(compileOnSave=False)
        )
        released.edit_json(
            "markcom-web-config/package.json",
            lambda data: data.update(dependencies=dict(reversed(data["dependencies"].items()))),
        )

    tags = released.origin_tags()
    released.push_to_main(outside)
    pushed = released.origin_main()
    assert main() == 0
    assert released.origin_tags() == tags
    assert released.origin_main() == pushed


def test_code_change_gets_the_next_patch_in_a_release_commit(released):
    old = declared(released, "markcom")
    new = bumped(old, "patch")
    released.push_to_main(lambda: released.append("markcom/src/markcom/runner.py", "\n# x\n"))
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


def test_runtime_dependency_change_gets_the_next_patch(released):
    new = bumped(declared(released, "markcom-i18n"), "patch")
    released.push_to_main(
        lambda: released.edit_json(
            "markcom-i18n/package.json",
            lambda data: data["dependencies"].update({"zz-runtime": "^1.0.0"}),
        )
    )
    assert main() == 0
    assert released.tagged_commit(f"markcom-i18n-v{new}") == released.origin_main()


def test_web_config_prettier_json_counts_as_code(released):
    new = bumped(declared(released, "markcom-web-config"), "patch")
    released.push_to_main(
        lambda: released.edit_json(
            "markcom-web-config/prettier.json", lambda data: data.update(zzRule=True)
        )
    )
    assert main() == 0
    assert f"markcom-web-config-v{new}" in released.origin_tags()


def test_several_libraries_share_one_release_commit(released):
    markcom = bumped(declared(released, "markcom"), "patch")
    old_i18n = declared(released, "markcom-i18n")
    i18n = bumped(old_i18n, "patch")

    def both():
        released.append("markcom/src/markcom/runner.py", "\n# x\n")
        released.append("markcom-i18n/src/vite.ts", "// x\n")

    released.push_to_main(both)
    pushed = released.origin_main()
    assert main() == 0
    release = released.origin_main()
    assert release.parents == (pushed,)
    assert released.tagged_commit(f"markcom-v{markcom}") == release
    assert released.tagged_commit(f"markcom-i18n-v{i18n}") == release
    assert f"markcom {markcom}" in release.message
    assert f"markcom-i18n {i18n}" in release.message
    assert changed_lines(released, pushed, release, "markcom-i18n/package-lock.json") == [
        f'-  "version": "{old_i18n}",',
        f'+  "version": "{i18n}",',
        f'-      "version": "{old_i18n}",',
        f'+      "version": "{i18n}",',
    ]


def test_version_raised_by_hand_fails(released, capsys):
    tags = released.origin_tags()
    released.push_to_main(
        lambda: released.set_npm_version("markcom-web-config", "99.0.0", lock=True)
    )
    assert main() == 1
    assert "markcom-web-config: version 99.0.0 differs from the last release" in (
        capsys.readouterr().out
    )
    assert released.origin_tags() == tags


def test_lower_version_fails_before_anything_is_released(released, capsys):
    def lower_and_change():
        released.set_markcom_version("0.0.1")
        released.append("markcom-i18n/src/vite.ts", "// x\n")

    tags = released.origin_tags()
    released.push_to_main(lower_and_change)
    pushed = released.origin_main()
    assert main() == 1
    assert "markcom: version 0.0.1 differs from the last release" in capsys.readouterr().out
    assert released.origin_tags() == tags
    assert released.origin_main() == pushed


def test_non_x_y_z_version_fails(released, capsys):
    tags = released.origin_tags()
    released.push_to_main(lambda: released.set_npm_version("markcom-web-config", "99.0.0-rc.1"))
    assert main() == 1
    assert "markcom-web-config: version 99.0.0-rc.1" in capsys.readouterr().out
    assert released.origin_tags() == tags


def test_main_moved_on_releases_nothing(released, capsys):
    tags = released.origin_tags()
    released.push_to_main(lambda: released.append("markcom/src/markcom/runner.py", "\n# x\n"))
    run_commit = released.repo.head.commit
    released.push_to_main(lambda: released.append("README.md", "\nx\n"))
    newer = released.origin_main()
    released.repo.git.checkout(run_commit.hexsha)
    assert main() == 0
    assert "main moved on" in capsys.readouterr().out
    assert released.origin_tags() == tags
    assert released.origin_main() == newer


def test_minor_label_bumps_only_the_libraries_that_changed(released, monkeypatch):
    monkeypatch.setenv("RELEASE_LABELS", "documentation\nrelease:minor")
    new = bumped(declared(released, "markcom"), "minor")
    tags = released.origin_tags()
    released.push_to_main(lambda: released.append("markcom/src/markcom/runner.py", "\n# x\n"))
    assert main() == 0
    assert released.origin_tags() - tags == {f"markcom-v{new}"}


def test_major_label_gives_the_next_major(released, monkeypatch):
    monkeypatch.setenv("RELEASE_LABELS", "release:major")
    new = bumped(declared(released, "markcom-i18n"), "major")
    released.push_to_main(lambda: released.append("markcom-i18n/src/vite.ts", "// x\n"))
    assert main() == 0
    assert f"markcom-i18n-v{new}" in released.origin_tags()


def test_missing_labels_variable_fails(clone, monkeypatch, capsys):
    monkeypatch.delenv("RELEASE_LABELS", raising=False)
    tags = clone.origin_tags()
    assert main() == 1
    assert "RELEASE_LABELS" in capsys.readouterr().out
    assert clone.origin_tags() == tags


def test_rejected_push_fails_without_tags(released, capsys):
    tags = released.origin_tags()
    released.push_to_main(lambda: released.append("markcom/src/markcom/runner.py", "\n# x\n"))
    hook = released.path.parent / "origin.git" / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    assert main() == 1
    assert "release failed" in capsys.readouterr().out
    assert released.origin_tags() == tags
