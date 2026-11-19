from release_tools.versions_unchanged import main

# Versions are relative to whatever the clone holds: 0.0.1 is lower, 99.x higher.


def test_unchanged_versions_pass(clone):
    clone.merge_pr(lambda: None)
    assert main() == 0


def test_raised_version_fails(clone, capsys):
    clone.merge_pr(lambda: clone.set_markcom_version("99.0.0"))
    assert main() == 1
    assert "markcom: version changed from " in capsys.readouterr().out


def test_lowered_version_fails(clone, capsys):
    clone.merge_pr(lambda: clone.set_npm_version("markcom-i18n", "0.0.1"))
    assert main() == 1
    assert "markcom-i18n: version changed from " in capsys.readouterr().out


def test_non_x_y_z_version_fails(clone, capsys):
    clone.merge_pr(lambda: clone.set_npm_version("markcom-web-config", "99.0.0-rc.1"))
    assert main() == 1
    assert "markcom-web-config: version 99.0.0-rc.1" in capsys.readouterr().out


def test_unreadable_version_fails(clone, capsys):
    clone.merge_pr(lambda: clone.write("markcom-i18n/package.json", "{ broken"))
    assert main() == 1
    assert "could not read markcom-i18n's version" in capsys.readouterr().out


def test_every_library_is_reported(clone, capsys):
    def change_two():
        clone.set_markcom_version("99.0.0")
        clone.set_npm_version("markcom-i18n", "99.0.0")

    clone.merge_pr(change_two)
    main()
    out = capsys.readouterr().out
    assert "markcom: version changed" in out
    assert "markcom-i18n: version changed" in out
