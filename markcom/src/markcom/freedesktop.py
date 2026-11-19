"""Linux notifications: Notify over D-Bus with a `desktop-entry` hint and a matching .desktop
file, which KDE Plasma needs before it keeps a timed-out notification in its history."""

import asyncio
import configparser
import logging
from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Protocol, override

from dbus_fast import BusType, Message, MessageType, Variant
from dbus_fast.aio import MessageBus
from dbus_fast.errors import DBusFastError
from desktop_notifier import Urgency
from slugify import slugify
from xdg_base_dirs import xdg_data_dirs, xdg_data_home

from markcom.config import CONFIG
from markcom.notification_backend import NotificationBackend, NotificationError

logger: logging.Logger = logging.getLogger(__name__)

MS_PER_SEC: int = 1000
ENTRY_SECTION: str = "Desktop Entry"
APPLICATIONS: str = "applications"
DESKTOP_SUFFIX: str = ".desktop"
NOTIFICATIONS_NAME: str = "org.freedesktop.Notifications"
NOTIFICATIONS_PATH: str = "/org/freedesktop/Notifications"
NOTIFY: str = "Notify"
# app_name, replaces_id, app_icon, summary, body, actions, hints, expire_timeout
NOTIFY_SIGNATURE: str = "susssasa{sv}i"
# replaces_id 0: a new notification, not a replacement
NEW_NOTIFICATION: int = 0
DESKTOP_ENTRY_HINT: str = "desktop-entry"
URGENCY_HINT: str = "urgency"
# D-Bus type codes of the two hints
STRING_TYPE: str = "s"
BYTE_TYPE: str = "y"
# libdbus's and sd-bus's default wait for a reply; dbus-fast has none of its own.
REPLY_TIMEOUT_SEC: float = 25
# What a failed connection or call raises; EOFError when the bus hangs up mid-call.
DBUS_ERRORS: tuple[type[Exception], ...] = (DBusFastError, EOFError)
# A malformed or non-UTF-8 existing .desktop file is left as it is: it may be another app's.
DESKTOP_FILE_ERRORS: tuple[type[Exception], ...] = (
    OSError,
    configparser.Error,
    UnicodeDecodeError,
)


# The spec's urgency bytes, named like desktop_notifier's Urgency so one maps to the other by name.
class FreedesktopUrgency(IntEnum):
    Low = 0
    Normal = 1
    Critical = 2


@dataclass(frozen=True)
class NotifyCall:
    app_name: str
    icon: str
    title: str
    message: str
    urgency: Urgency
    desktop_entry: str
    timeout_ms: int


class NotificationBus(Protocol):
    def notify(self, call: NotifyCall) -> None: ...


class SessionConnection:
    """The user's session bus, connected for one `async with` block."""

    def __init__(self) -> None:
        self._bus: MessageBus = MessageBus(bus_type=BusType.SESSION)

    async def __aenter__(self) -> MessageBus:
        return await self._bus.connect()

    async def __aexit__(self, *_: object) -> None:
        self._bus.disconnect()


class SessionBus(NotificationBus):
    def __init__(self, reply_timeout_sec: float) -> None:
        self._reply_timeout_sec: float = reply_timeout_sec

    @override
    def notify(self, call: NotifyCall) -> None:
        # dbus-fast is async only; its own loop on a worker thread works whether or not the
        # caller's thread already runs one, as uvicorn's does
        with ThreadPoolExecutor(max_workers=1) as worker:
            sending: Future[int] = worker.submit(self._send, call)
            try:
                notification_id: int = sending.result()
            except DBUS_ERRORS as error:
                raise NotificationError(str(error)) from error
        logger.debug("bus showed notification %d", notification_id)

    def _send(self, call: NotifyCall) -> int:
        return asyncio.run(self._notify(call))

    async def _notify(self, call: NotifyCall) -> int:
        async with (
            asyncio.timeout(self._reply_timeout_sec),
            SessionConnection() as bus,
        ):
            reply: Message = await bus.call(
                Message(
                    destination=NOTIFICATIONS_NAME,
                    path=NOTIFICATIONS_PATH,
                    interface=NOTIFICATIONS_NAME,
                    member=NOTIFY,
                    signature=NOTIFY_SIGNATURE,
                    body=[
                        call.app_name,
                        NEW_NOTIFICATION,
                        call.icon,
                        call.title,
                        call.message,
                        [],
                        {
                            DESKTOP_ENTRY_HINT: Variant(STRING_TYPE, call.desktop_entry),
                            URGENCY_HINT: Variant(BYTE_TYPE, FreedesktopUrgency[call.urgency.name]),
                        },
                        call.timeout_ms,
                    ],
                )
            )
        if reply.message_type is MessageType.ERROR:
            rejected: str = f"{reply.error_name}: {reply.body}"
            raise NotificationError(rejected)
        notification_id: int = reply.body[0]
        return notification_id


class MissingDesktopEntryError(ValueError): ...


class DesktopEntryConflictError(ValueError): ...


class FreedesktopBackend(NotificationBackend):
    def __init__(self, app_name: str, icon: Path, desktop_entry: str, bus: NotificationBus) -> None:
        self._app_name: str = app_name
        self._icon: str = str(icon.resolve())
        self._desktop_entry: str = desktop_entry
        self._bus: NotificationBus = bus

    @override
    def send(self, title: str, message: str, urgency: Urgency, display_sec: int) -> None:
        logger.debug(
            "notifying %r as %s, urgency %s, %d s", title, self._desktop_entry, urgency, display_sec
        )
        self._bus.notify(
            NotifyCall(
                self._app_name,
                self._icon,
                title,
                message,
                urgency,
                self._desktop_entry,
                display_sec * MS_PER_SEC,
            )
        )


def find_desktop_entry(desktop_entry: str, data_dirs: Sequence[Path]) -> str:
    if not any(
        (data_dir / APPLICATIONS / f"{desktop_entry}{DESKTOP_SUFFIX}").is_file()
        for data_dir in data_dirs
    ):
        searched: str = ", ".join(str(data_dir / APPLICATIONS) for data_dir in data_dirs)
        missing: str = f"no {desktop_entry}{DESKTOP_SUFFIX} in {searched}"
        raise MissingDesktopEntryError(missing)
    logger.debug("desktop entry %s is installed", desktop_entry)
    return desktop_entry


class DesktopFile(configparser.RawConfigParser):
    """A .desktop file: INI syntax, but its keys are case-sensitive."""

    @override
    def optionxform(self, optionstr: str) -> str:
        return optionstr


def install_desktop_entry(app_name: str, icon: Path, data_home: Path) -> str:
    desktop_entry: str = slugify(app_name)
    applications_dir: Path = data_home / APPLICATIONS
    path: Path = applications_dir / f"{desktop_entry}{DESKTOP_SUFFIX}"
    try:
        if path.is_file():
            existing: DesktopFile = DesktopFile()
            existing.read(path, encoding="utf-8")
            if (
                existing.get(ENTRY_SECTION, CONFIG.desktop_entry_owner_key, fallback=None)
                != app_name
            ):
                conflict: str = (
                    f"{path} belongs to another application; pass its ID as desktop_entry"
                )
                raise DesktopEntryConflictError(conflict)
            logger.debug("%s is already this app's", path)
            return desktop_entry
        entry: DesktopFile = DesktopFile()
        # Exec is required by the spec; NoDisplay keeps the entry out of application menus.
        entry[ENTRY_SECTION] = {
            "Type": "Application",
            "Name": app_name,
            "Icon": str(icon.resolve()),
            "Exec": "true",
            "NoDisplay": "true",
            CONFIG.desktop_entry_owner_key: app_name,
        }
        applications_dir.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as file:
            entry.write(file, space_around_delimiters=False)
        logger.info("wrote %s", path)
    except DESKTOP_FILE_ERRORS:
        # Notifications still show; Plasma only leaves them out of its history.
        logger.exception("could not read or write %s for notification history", path)
    return desktop_entry


def open_backend(app_name: str, icon: Path, desktop_entry: str | None) -> NotificationBackend:
    # The XDG search order: the user's own data folder, then the system's.
    entry: str = (
        install_desktop_entry(app_name, icon, xdg_data_home())
        if desktop_entry is None
        else find_desktop_entry(desktop_entry, [xdg_data_home(), *xdg_data_dirs()])
    )
    logger.info("notifications name the desktop entry %s", entry)
    return FreedesktopBackend(app_name, icon, entry, SessionBus(REPLY_TIMEOUT_SEC))
