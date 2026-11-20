"""What markcom.window and its window process (markcom.window_process) send each other. No Qt
imports, so the app's process loads none of QtWebEngine to build them."""

from pathlib import Path
from typing import ClassVar

from pydantic import ConfigDict, HttpUrl

from markcom.config import LogLevel, StrictModel

# Holds the WindowSpec as JSON. Not argv: any local user can read a process's argv, and the URL
# may carry a token; only the owner can read its environment.
SPEC_VARIABLE: str = "MARKCOM_WINDOW_SPEC"
# The app's one command, a line on the window process's stdin: bring the window back. Closing
# stdin closes the window, and the process ends with it.
SHOW: bytes = b"show"
LINE_END: bytes = b"\n"


class _BinaryJson(StrictModel):
    # JSON has no bytes; base64 also keeps each message on one line
    model_config: ClassVar[ConfigDict] = ConfigDict(
        ser_json_bytes="base64", val_json_bytes="base64"
    )


class WindowSpec(_BinaryJson):
    """What the window process shows, and how; in its SPEC_VARIABLE."""

    title: str
    url: HttpUrl
    icon: Path
    # The app's level, so the window process logs as much as the app does.
    log_level: LogLevel
    # QWidget.saveGeometry from the last window's report; None on the first open, which takes
    # config.json's size.
    geometry: bytes | None


class WindowReport(_BinaryJson):
    """A line on the window process's stdout, sent each time the window is minimised, brought back,
    resized, moved or closed."""

    minimised: bool
    # QWidget.saveGeometry: size and maximised state, for the next window.
    geometry: bytes
