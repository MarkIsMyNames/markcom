from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import HttpUrl, ValidationError

from markcom.window_messages import WindowReport, WindowSpec


@given(
    title=st.text(),
    port=st.integers(1, 65535),
    icon=st.text(st.characters(codec="utf-8", exclude_characters="\x00/"), min_size=1),
    level=st.sampled_from(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    geometry=st.none() | st.binary(),
)
def test_a_spec_reads_back_from_its_json(title, port, icon, level, geometry):
    spec = WindowSpec(
        title=title,
        url=HttpUrl(f"http://127.0.0.1:{port}/"),
        icon=Path("/") / icon,
        log_level=level,
        geometry=geometry,
    )
    assert WindowSpec.model_validate_json(spec.model_dump_json()) == spec


@given(minimised=st.booleans(), geometry=st.binary())
def test_a_report_reads_back_from_its_json_on_one_line(minimised, geometry):
    line = WindowReport(minimised=minimised, geometry=geometry).model_dump_json()
    assert "\n" not in line
    assert WindowReport.model_validate_json(line) == WindowReport(
        minimised=minimised, geometry=geometry
    )


@pytest.mark.parametrize(
    "line", [b"Qt says hello", b'{"minimised": false}', b'{"minimised": 1, "geometry": ""}']
)
def test_a_line_that_is_not_a_report_is_refused(line):
    with pytest.raises(ValidationError):
        WindowReport.model_validate_json(line)


def test_an_unknown_log_level_is_refused():
    with pytest.raises(ValidationError):
        WindowSpec(
            title="App",
            url=HttpUrl("http://127.0.0.1:8080/"),
            icon=Path("/icons/app.png"),
            log_level="LOUD",
            geometry=None,
        )
