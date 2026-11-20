"""The window process's spec. No Qt imports: the app's process never loads QtWebEngine."""

from pathlib import Path

from pydantic import HttpUrl

from markcom.config import LogLevel, StrictModel

# env, not argv: any local user can read argv, and the URL may carry a token
SPEC_VARIABLE: str = "MARKCOM_WINDOW_SPEC"


class WindowSpec(StrictModel):
    title: str
    url: HttpUrl
    icon: Path
    # the app's, so the window logs as much
    log_level: LogLevel
