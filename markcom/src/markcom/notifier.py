import asyncio
import logging
import threading
from pathlib import Path

import desktop_notifier
from desktop_notifier import Icon, Urgency

logger: logging.Logger = logging.getLogger(__name__)

NEVER_EXPIRES_SEC: int = 0
# tray.py skips this thread's log records, see there
NOTIFIER_THREAD: str = "notifier"


class DesktopNotifier:
    def __init__(self, app_name: str, icon: Path) -> None:
        # relative icon path fails every send
        self._notifier: desktop_notifier.DesktopNotifier = desktop_notifier.DesktopNotifier(
            app_name=app_name, app_icon=Icon(path=icon.resolve())
        )
        # D-Bus connection stays bound to the loop that opened it; daemon so exit never waits
        self._loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever, name=NOTIFIER_THREAD, daemon=True).start()
        logger.info("desktop notifications for %r", app_name)

    def send(self, title: str, message: str, urgency: Urgency, display_sec: int) -> None:
        # blocks until desktop has it, so a log record just before exit still shows
        logger.debug("notifying %r, urgency %s, %d s", title, urgency, display_sec)
        asyncio.run_coroutine_threadsafe(
            self._notifier.send(title=title, message=message, urgency=urgency, timeout=display_sec),
            self._loop,
        ).result()
