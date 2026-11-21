import pytest
from semver import Version

from release_tools.config import Labels
from release_tools.versions import BumpLevel, bump_level


@pytest.mark.parametrize(
    ("level", "expected"),
    [(BumpLevel.PATCH, "0.4.2"), (BumpLevel.MINOR, "0.5.0"), (BumpLevel.MAJOR, "1.0.0")],
)
def test_bumps_by_level(level, expected):
    assert str(Version.parse("0.4.1").next_version(level)) == expected


@pytest.mark.parametrize(
    ("labels", "expected"),
    [
        ([], BumpLevel.PATCH),
        (["documentation"], BumpLevel.PATCH),
        (["release:minor"], BumpLevel.MINOR),
        (["release:major"], BumpLevel.MAJOR),
        (["release:minor", "release:major"], BumpLevel.MAJOR),
    ],
)
def test_bump_level_comes_from_labels(labels, expected):
    assert bump_level(labels, Labels(minor="release:minor", major="release:major")) == expected
