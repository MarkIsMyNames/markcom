"""Desktop notifications through desktop-notifier, best effort: it logs a failed send itself, at
WARNING, and never raises it."""

import asyncio
import logging
import threading
from pathlib import Path

import desktop_notifier
from desktop_notifier import Icon, Urgency

logger: logging.Logger = logging.getLogger(__name__)

# The freedesktop notification spec's timeout for "stay until dismissed".
NEVER_EXPIRES_SEC: int = 0
# The thread every send runs on; tray.py skips its log records, see there.
NOTIFIER_THREAD: str = "notifier"


class DesktopNotifier:
    """Sends from any thread, even one already running an event loop, as uvicorn's does."""

    def __init__(self, app_name: str, icon: Path) -> None:
        # desktop-notifier needs an absolute icon path; a relative one fails every send.
        self._notifier: desktop_notifier.DesktopNotifier = desktop_notifier.DesktopNotifier(
            app_name=app_name, app_icon=Icon(path=icon.resolve())
        )
        # Its own loop for the app's lifetime: the D-Bus connection stays bound to the loop
        # that opened it. A daemon thread, so it never holds up exit.
        self._loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever, name=NOTIFIER_THREAD, daemon=True).start()
        logger.info("desktop notifications for %r", app_name)

    def send(self, title: str, message: str, urgency: Urgency, display_sec: int) -> None:
        """Show a notification for `display_sec`; NEVER_EXPIRES_SEC (0) keeps it until the user
        dismisses it. Returns once the desktop has it, so a log record just before exit still
        shows."""
        logger.debug("notifying %r, urgency %s, %d s", title, urgency, display_sec)
        asyncio.run_coroutine_threadsafe(
            self._notifier.send(title=title, message=message, urgency=urgency, timeout=display_sec),
            self._loop,
        ).result()
