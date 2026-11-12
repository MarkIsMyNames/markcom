"""Desktop notifications, best effort: a missing or failing backend is logged, never raised."""

import logging
from pathlib import Path

from dbus_fast.errors import DBusError
from desktop_notifier import DesktopNotifierSync, Icon, Urgency

logger: logging.Logger = logging.getLogger(__name__)

# What an unavailable notification service or a failed send raises.
BACKEND_ERRORS: tuple[type[Exception], ...] = (OSError, RuntimeError, ImportError, DBusError)
# The freedesktop notification spec's timeout for "stay until dismissed".
NEVER_EXPIRES_SEC: int = 0


class DesktopNotifier:
    """Sends each notification straight away, from the caller's thread."""

    def __init__(self, app_name: str, icon: Path) -> None:
        # None: the notification service was unavailable at start-up.
        self._backend: DesktopNotifierSync | None
        try:
            self._backend = DesktopNotifierSync(app_name=app_name, app_icon=Icon(path=icon))
        except BACKEND_ERRORS:
            logger.exception("desktop notifications unavailable")
            self._backend = None

    def send(
        self, title: str, message: str, urgency: Urgency, display_sec: int | None = None
    ) -> None:
        """Show a notification for `display_sec`; None keeps it until the user dismisses it."""
        if self._backend is None:
            return
        timeout_sec: int = NEVER_EXPIRES_SEC if display_sec is None else display_sec
        try:
            self._backend.send(title=title, message=message, urgency=urgency, timeout=timeout_sec)
        except BACKEND_ERRORS as error:
            logger.warning("desktop notification failed: %s", error)
