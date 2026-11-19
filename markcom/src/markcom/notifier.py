"""Desktop notifications, best effort: a missing or failing backend is logged, never raised."""

import logging
import platform
from pathlib import Path
from typing import override

from desktop_notifier import DesktopNotifierSync, Icon, Urgency

from markcom import freedesktop
from markcom.notification_backend import NotificationBackend

logger: logging.Logger = logging.getLogger(__name__)

# What an unavailable notification service or a failed send raises.
BACKEND_ERRORS: tuple[type[Exception], ...] = (OSError, RuntimeError, ImportError)
# The freedesktop notification spec's timeout for "stay until dismissed".
NEVER_EXPIRES_SEC: int = 0
# What platform.system() returns on Linux; the standard library has no enum for it.
LINUX: str = "Linux"


class DesktopNotifierBackend(NotificationBackend):
    """macOS and Windows, through desktop-notifier."""

    def __init__(self, app_name: str, icon: Path) -> None:
        self._notifier: DesktopNotifierSync = DesktopNotifierSync(
            app_name=app_name, app_icon=Icon(path=icon)
        )

    @override
    def send(self, title: str, message: str, urgency: Urgency, display_sec: int) -> None:
        logger.debug("notifying %r, urgency %s, %d s", title, urgency, display_sec)
        self._notifier.send(title=title, message=message, urgency=urgency, timeout=display_sec)


def _open_backend(app_name: str, icon: Path, desktop_entry: str | None) -> NotificationBackend:
    system: str = platform.system()
    if system == LINUX:
        logger.debug("%s: notifications over D-Bus", system)
        return freedesktop.open_backend(app_name, icon, desktop_entry)
    logger.debug("%s: notifications through desktop-notifier", system)
    return DesktopNotifierBackend(app_name, icon)


class DesktopNotifier:
    """Sends each notification straight away, from the caller's thread."""

    def __init__(self, app_name: str, icon: Path, desktop_entry: str | None = None) -> None:
        """`desktop_entry`: the app's installed .desktop file ID (Linux); None writes one."""
        # None: the notification service was unavailable at start-up.
        self._backend: NotificationBackend | None
        try:
            self._backend = _open_backend(app_name, icon, desktop_entry)
        except BACKEND_ERRORS:
            logger.error("desktop notifications unavailable")
            self._backend = None
        else:
            logger.info("desktop notifications through %s", type(self._backend).__name__)

    def send(self, title: str, message: str, urgency: Urgency, display_sec: int) -> None:
        """Show a notification for `display_sec`; NEVER_EXPIRES_SEC (0) keeps it until the user
        dismisses it."""
        if self._backend is None:
            logger.debug("no notification backend, so %r is dropped", title)
            return
        try:
            self._backend.send(title, message, urgency, display_sec)
        except BACKEND_ERRORS:
            logger.error("desktop notification failed")
