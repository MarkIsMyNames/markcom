import json
import os
import tomllib

import pytest

from release_tools.versions_unchanged import main

# Versions are relative to whatever the clone holds: 0.0.1 is lower, 99.x higher.


def commit_on(clone, change):
    change()
    clone.repo.git.add("-A")
    clone.repo.git.commit("--allow-empty", "-m", "branch commit")


def test_unchanged_versions_pass(clone):
    clone.merge_pr(lambda: None)
    assert main() == os.EX_OK


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda clone: clone.set_markcom_version("99.0.0"), "markcom: version changed from "),
        (
            lambda clone: clone.set_npm_version("markcom-i18n", "0.0.1"),
            "markcom-i18n: version changed from ",
        ),
        (
            lambda clone: clone.set_npm_version("markcom-web-config", "1.0"),
            "markcom-web-config: version 1.0 is not of the form X.Y.Z",
        ),
        (
            lambda clone: clone.write("markcom-i18n/package.json", "{ broken"),
            "could not read markcom-i18n's version",
        ),
    ],
)
def test_changed_or_bad_version_fails(clone, capsys, change, message):
    clone.merge_pr(lambda: change(clone))
    assert main() == os.EX_DATAERR
    assert message in capsys.readouterr().out


def test_build_metadata_added_to_a_version_fails(clone):
    text = (clone.path / "markcom" / "pyproject.toml").read_text(encoding="utf-8")
    version = tomllib.loads(text)["project"]["version"]
    clone.merge_pr(lambda: clone.set_markcom_version(f"{version}+build"))
    assert main() == os.EX_DATAERR


def test_every_library_is_reported(clone, capsys):
    def change_two():
        clone.set_markcom_version("99.0.0")
        clone.set_npm_version("markcom-i18n", "99.0.0")

    clone.merge_pr(change_two)
    main()
    out = capsys.readouterr().out
    assert "markcom: version changed" in out
    assert "markcom-i18n: version changed" in out


def test_missing_release_config_fails(clone, capsys):
    clone.merge_pr(lambda: clone.repo.git.rm("-q", "release.json"))
    assert main() == os.EX_CONFIG
    assert "release.json" in capsys.readouterr().out


def test_library_new_in_the_pull_request_passes(clone, capsys):
    def add_library():
        (clone.path / "newlib").mkdir()
        clone.write("newlib/package.json", '{"name": "newlib", "version": "0.1.0"}\n')
        config = json.loads((clone.path / "release.json").read_text(encoding="utf-8"))
        config["libraries"].append(
            {
                "name": "newlib",
                "kind": "npm",
                "path": "newlib",
                "tag_prefix": "newlib-v",
                "extra_code": [],
            }
        )
        clone.write("release.json", json.dumps(config))

    clone.merge_pr(add_library)
    assert main() == os.EX_OK
    assert "newlib: 0.1.0, new" in capsys.readouterr().out


def test_a_version_changed_earlier_on_a_branch_fails_at_its_head(clone, capsys):
    clone.repo.git.switch("-c", "pr")
    commit_on(clone, lambda: clone.set_markcom_version("99.0.0"))
    commit_on(clone, lambda: clone.append("README.md", "\nlater commit\n"))
    assert main() == os.EX_DATAERR
    assert "markcom: version changed from " in capsys.readouterr().out


def test_a_release_on_main_after_the_branch_left_passes_at_its_head(clone):
    clone.repo.git.switch("-c", "pr")
    commit_on(clone, lambda: clone.append("README.md", "\nbranch commit\n"))
    clone.repo.git.switch("main")
    clone.push_to_main(lambda: clone.set_markcom_version("99.0.0"))
    clone.repo.git.switch("pr")
    assert main() == os.EX_OK


def test_a_release_on_main_after_the_merge_commit_was_made_passes(clone):
    clone.merge_pr(lambda: None)
    merged = clone.repo.head.commit
    clone.repo.git.switch("-c", "later-main", "HEAD^1")
    clone.push_to_main(lambda: clone.set_markcom_version("99.0.0"))
    clone.repo.git.checkout(merged.hexsha)
    assert main() == os.EX_OK
