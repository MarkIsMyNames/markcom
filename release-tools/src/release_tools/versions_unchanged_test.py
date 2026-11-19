import pytest

from release_tools.versions_unchanged import main

# Versions are relative to whatever the clone holds: 0.0.1 is lower, 99.x higher.


def test_unchanged_versions_pass(clone):
    clone.merge_pr(lambda: None)
    assert main() == 0


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda clone: clone.set_markcom_version("99.0.0"), "markcom: version changed from "),
        (
            lambda clone: clone.set_npm_version("markcom-i18n", "0.0.1"),
            "markcom-i18n: version changed from ",
        ),
        (
            lambda clone: clone.set_npm_version("markcom-web-config", "99.0.0-rc.1"),
            "markcom-web-config: version 99.0.0-rc.1 is not of the form X.Y.Z",
        ),
        (
            lambda clone: clone.write("markcom-i18n/package.json", "{ broken"),
            "could not read markcom-i18n's version",
        ),
    ],
)
def test_changed_or_bad_version_fails(clone, capsys, change, message):
    clone.merge_pr(lambda: change(clone))
    assert main() == 1
    assert message in capsys.readouterr().out


def test_every_library_is_reported(clone, capsys):
    def change_two():
        clone.set_markcom_version("99.0.0")
        clone.set_npm_version("markcom-i18n", "99.0.0")

    clone.merge_pr(change_two)
    main()
    out = capsys.readouterr().out
    assert "markcom: version changed" in out
    assert "markcom-i18n: version changed" in out
