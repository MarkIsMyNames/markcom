"""The window process's spec, apart from window.py so the window process needn't import the tray."""

from pathlib import Path

from pydantic import HttpUrl

from markcom.config import LogLevel, StrictModel

# The environment, not argv: any local user can read argv, and the URL may carry a token.
SPEC_VARIABLE: str = "MARKCOM_WINDOW_SPEC"


class WindowSpec(StrictModel):
    title: str
    url: HttpUrl
    icon: Path
    # The app's, so the window logs as much as it does.
    log_level: LogLevel
