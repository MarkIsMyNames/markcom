import pytest

from release_tools.versions import InvalidVersionError, Version


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
