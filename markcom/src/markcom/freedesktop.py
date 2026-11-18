"""Linux notifications: Notify over D-Bus with a `desktop-entry` hint and a matching .desktop
file, which KDE Plasma needs before it keeps a timed-out notification in its history."""

import configparser
import logging
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Protocol, override

from desktop_notifier import Urgency
from sdbus import SdBusBaseError, sd_bus_open_user
from sdbus_block.notifications import FreedesktopNotifications
from slugify import slugify
from xdg_base_dirs import xdg_data_dirs, xdg_data_home

from markcom.config import CONFIG
from markcom.notification_backend import NotificationBackend, NotificationError

logger: logging.Logger = logging.getLogger(__name__)

MS_PER_SEC: int = 1000
ENTRY_SECTION: str = "Desktop Entry"
APPLICATIONS: str = "applications"
DESKTOP_SUFFIX: str = ".desktop"


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


class SessionBus(NotificationBus):
    @override
    def notify(self, call: NotifyCall) -> None:
        try:
            with closing(sd_bus_open_user()) as bus:
                notifications: FreedesktopNotifications = FreedesktopNotifications(bus)
                notification_id: int = notifications.notify(
                    app_name=call.app_name,
                    app_icon=call.icon,
                    summary=call.title,
                    body=call.message,
                    hints=notifications.create_hints(
                        desktop_entry_name=call.desktop_entry,
                        urgency=FreedesktopUrgency[call.urgency.name],
                    ),
                    expire_timeout=call.timeout_ms,
                )
                logger.debug("bus showed notification %d", notification_id)
        except SdBusBaseError as error:
            raise NotificationError(str(error)) from error


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
    # None: installed in none of the data folders
    found: Path | None = next(
        (
            path
            for data_dir in data_dirs
            if (path := data_dir / APPLICATIONS / f"{desktop_entry}{DESKTOP_SUFFIX}").is_file()
        ),
        None,
    )
    if found is None:
        searched: str = ", ".join(str(data_dir / APPLICATIONS) for data_dir in data_dirs)
        missing: str = f"no {desktop_entry}{DESKTOP_SUFFIX} in {searched}"
        raise MissingDesktopEntryError(missing)
    logger.debug("desktop entry %s found at %s", desktop_entry, found)
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
    except OSError:
        # Notifications still show; Plasma only leaves them out of its history.
        logger.warning("could not write %s for notification history", path, exc_info=True)
    return desktop_entry


def open_backend(app_name: str, icon: Path, desktop_entry: str | None) -> NotificationBackend:
    # The XDG search order: the user's own data folder, then the system's.
    entry: str = (
        install_desktop_entry(app_name, icon, xdg_data_home())
        if desktop_entry is None
        else find_desktop_entry(desktop_entry, [xdg_data_home(), *xdg_data_dirs()])
    )
    logger.info("notifications name the desktop entry %s", entry)
    return FreedesktopBackend(app_name, icon, entry, SessionBus())
