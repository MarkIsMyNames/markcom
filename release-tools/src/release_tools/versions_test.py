import pytest

from release_tools.config import Labels
from release_tools.versions import BumpLevel, InvalidVersionError, Version, bump_level


def test_parses_x_y_z():
    assert Version.parse("0.4.1") == Version(0, 4, 1)


def test_prints_as_x_y_z():
    assert str(Version(1, 20, 3)) == "1.20.3"


@pytest.mark.parametrize("text", ["1.0.0-rc.1", "1.0", "v1.0.0", "", "1.0.0 "])
def test_rejects_anything_but_x_y_z(text):
    with pytest.raises(InvalidVersionError):
        Version.parse(text)


def test_orders_by_number_not_text():
    assert Version.parse("0.10.0") > Version.parse("0.9.9")


@pytest.mark.parametrize(
    ("level", "expected"),
    [(BumpLevel.PATCH, "0.4.2"), (BumpLevel.MINOR, "0.5.0"), (BumpLevel.MAJOR, "1.0.0")],
)
def test_bumps_by_level(level, expected):
    assert str(Version.parse("0.4.1").bump(level)) == expected


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
