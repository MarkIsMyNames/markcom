import asyncio
import logging
import threading
from abc import ABC, abstractmethod
from concurrent.futures import Future
from enum import Enum
from pathlib import Path
from typing import override

from dbus_fast import Message, MessageType, Variant
from dbus_fast.aio import MessageBus

logger: logging.Logger = logging.getLogger(__name__)

NEVER_EXPIRES_SEC: int = 0
# tray.py skips this thread's log records, see there
NOTIFIER_THREAD: str = "notifier"

NOTIFICATIONS_SERVICE: str = "org.freedesktop.Notifications"
NOTIFICATIONS_PATH: str = "/org/freedesktop/Notifications"
NOTIFY: str = "Notify"
# app_name, replaces_id, app_icon, summary, body, actions, hints, expire_timeout
NOTIFY_SIGNATURE: str = "susssasa{sv}i"
NEW_NOTIFICATION: int = 0
MS_PER_SEC: int = 1000
URGENCY_HINT: str = "urgency"
# KDE Plasma keeps an expired notification in its history only with this hint
DESKTOP_ENTRY_HINT: str = "desktop-entry"


class Urgency(Enum):
    # values: freedesktop's urgency byte
    Low = 0
    Normal = 1
    Critical = 2


def _log_failure[T](sent: Future[T]) -> None:
    # fire and forget, so only this sees a failed send
    failure: BaseException | None = sent.exception()
    if failure is not None:
        logger.error("a notification failed", exc_info=failure)


class Notifier(ABC):
    def __init__(self) -> None:
        # D-Bus connection stays bound to the loop that opened it; daemon so exit never waits
        self._loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever, name=NOTIFIER_THREAD, daemon=True).start()

    @abstractmethod
    def send(self, title: str, message: str, urgency: Urgency, display_sec: int) -> None: ...


class FreedesktopNotifier(Notifier):
    """`desktop_entry`: the app's installed .desktop file ID, such as org.example.App."""

    def __init__(self, app_name: str, icon: Path, desktop_entry: str) -> None:
        super().__init__()
        self._app_name: str = app_name
        self._icon: str = icon.resolve().as_uri()
        self._desktop_entry: str = desktop_entry
        # blocks: a send must find the bus connected
        self._bus: MessageBus = asyncio.run_coroutine_threadsafe(
            self._connect(), self._loop
        ).result()
        logger.info("freedesktop notifications for %r as %s", app_name, desktop_entry)

    @staticmethod
    async def _connect() -> MessageBus:
        # MessageBus binds to the loop it is built on, so it is built on the notifier's
        return await MessageBus().connect()

    @override
    def send(self, title: str, message: str, urgency: Urgency, display_sec: int) -> None:
        logger.debug("notifying %r, urgency %s, %d s", title, urgency, display_sec)
        hints: dict[str, Variant] = {
            URGENCY_HINT: Variant("y", urgency.value),
            DESKTOP_ENTRY_HINT: Variant("s", self._desktop_entry),
        }
        notify: Message = Message(
            destination=NOTIFICATIONS_SERVICE,
            path=NOTIFICATIONS_PATH,
            interface=NOTIFICATIONS_SERVICE,
            member=NOTIFY,
            signature=NOTIFY_SIGNATURE,
            body=[
                self._app_name,
                NEW_NOTIFICATION,
                self._icon,
                title,
                message,
                [],
                hints,
                display_sec * MS_PER_SEC,
            ],
        )
        asyncio.run_coroutine_threadsafe(self._call(notify), self._loop).add_done_callback(
            _log_failure
        )

    async def _call(self, notify: Message) -> None:
        reply: Message | None = await self._bus.call(notify)
        # best effort: a refused send is logged, never raised
        if reply is not None and reply.message_type is MessageType.ERROR:
            logger.warning(
                "the desktop refused a notification: %s %s", reply.error_name, reply.body
            )
