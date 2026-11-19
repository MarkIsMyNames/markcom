from release_tools.version_increases import main

# Versions are relative to whatever the clone holds: 0.0.1 is lower, 99.x higher.


def test_unchanged_versions_pass(clone):
    clone.merge_pr(lambda: None)
    assert main() == 0


def test_raised_versions_pass(clone):
    def raise_all():
        clone.set_markcom_version("99.0.0")
        clone.set_npm_version("markcom-web-config", "99.1.0")
        clone.set_npm_version("markcom-i18n", "99.2.0")

    clone.merge_pr(raise_all)
    assert main() == 0


def test_lowered_markcom_fails_naming_both_versions(clone, capsys):
    clone.merge_pr(lambda: clone.set_markcom_version("0.0.1"))
    assert main() == 1
    assert "markcom: version 0.0.1 is lower than " in capsys.readouterr().out


def test_lowered_npm_package_fails(clone, capsys):
    clone.merge_pr(lambda: clone.set_npm_version("markcom-i18n", "0.0.1"))
    assert main() == 1
    assert "markcom-i18n: version 0.0.1 is lower than " in capsys.readouterr().out


def test_non_x_y_z_version_fails(clone, capsys):
    clone.merge_pr(lambda: clone.set_npm_version("markcom-web-config", "99.0.0-rc.1"))
    assert main() == 1
    assert "markcom-web-config: version 99.0.0-rc.1" in capsys.readouterr().out


def test_unreadable_version_fails(clone, capsys):
    clone.merge_pr(lambda: clone.write("markcom-i18n/package.json", "{ broken"))
    assert main() == 1
    assert "could not read markcom-i18n's version" in capsys.readouterr().out


def test_every_library_is_reported(clone, capsys):
    def lower_two():
        clone.set_markcom_version("0.0.1")
        clone.set_npm_version("markcom-i18n", "0.0.1")

    clone.merge_pr(lower_two)
    main()
    out = capsys.readouterr().out
    assert "markcom: version 0.0.1" in out
    assert "markcom-i18n: version 0.0.1" in out
