"""A system tray icon (Qt): left click runs the app's main action, right click shows its other
actions and Quit. Notifications sent through it, the app's ERROR and CRITICAL log records among
them, count as unread, shown as a badge on the icon, until the next left click."""

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from traceback import format_exception_only
from typing import Self, override

from desktop_notifier import Urgency
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from markcom.config import CONFIG
from markcom.notifier import NEVER_EXPIRES_SEC, DesktopNotifier
from markcom.notifier import logger as notifier_logger

logger: logging.Logger = logging.getLogger(__name__)

# What a menu action may fail with (files: OSError, ValueError; browser: OSError; desktop:
# RuntimeError). They are logged so the tray keeps running; anything else is a bug, logged too.
ACTION_ERRORS: tuple[type[Exception], ...] = (OSError, ValueError, RuntimeError)
# What turning a log record into a notification may fail with: a malformed log call (TypeError,
# ValueError, KeyError) or a Qt object already deleted (RuntimeError).
NOTIFY_ERRORS: tuple[type[Exception], ...] = (TypeError, ValueError, KeyError, RuntimeError)
# Where the badge is drawn, badge_margin pixels in from the icon's bottom-right corner.
BADGE_RECT: QRectF = QRectF(
    CONFIG.tray.icon_size - CONFIG.tray.badge_size - CONFIG.tray.badge_margin,
    CONFIG.tray.icon_size - CONFIG.tray.badge_size - CONFIG.tray.badge_margin,
    CONFIG.tray.badge_size,
    CONFIG.tray.badge_size,
)


class TrayTarget(ABC):
    """What a left click opens or closes. The app may also open or close it outside the tray, so
    is_open() reports the real state each time rather than the tray remembering its last click.

    Called on the GUI thread, so each must return fast; slow work goes to the target's own
    worker."""

    @abstractmethod
    def is_open(self) -> bool: ...

    @abstractmethod
    def open(self) -> None:
        """Returns once is_open() reports True, so the next click closes it."""

    @abstractmethod
    def close(self) -> None:
        """Returns once is_open() reports False, so the next click opens it."""


# Where a log record's notification goes: Tray.send.
type Send = Callable[[str, str, Urgency, int], None]


class _RecordNotifications(logging.Handler):
    """ERROR records shown for error_display_sec, CRITICAL ones until dismissed. The title is the
    level; the body is the message, then the record's exception (type and text, and each one in a
    group) without its traceback."""

    def __init__(self, send: Send, error_display_sec: int) -> None:
        super().__init__(logging.ERROR)
        self._send: Send = send
        self._error_display_sec: int = error_display_sec

    @override
    def filter(self, record: logging.LogRecord) -> bool | logging.LogRecord:
        # the notifier's own failure: sending it would fail and log again, without end
        return record.name != notifier_logger.name and super().filter(record)

    @override
    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._notify(record)
        except NOTIFY_ERRORS:
            # logging's contract: a handler never raises into the app's log call;
            # handleError reports the failure on stderr instead
            self.handleError(record)

    def _notify(self, record: logging.LogRecord) -> None:
        title: str = record.levelname.capitalize()
        body: str = record.getMessage()
        # None: no exception, or exc_info=True outside an except block
        error: BaseException | None = None if record.exc_info is None else record.exc_info[1]
        if error is not None:
            # the traceback is for the log; a notification says only why
            body = f"{body}: {''.join(format_exception_only(error, show_group=True)).strip()}"
        if record.levelno >= logging.CRITICAL:
            self._send(title, body, Urgency.Critical, NEVER_EXPIRES_SEC)
            return
        # Normal, not critical: desktops keep critical ones until dismissed, ignoring display_sec
        self._send(title, body, Urgency.Normal, self._error_display_sec)


@dataclass(frozen=True)
class TrayNotifications:
    """Where the tray's notifications go, and how long an ERROR log record's notification shows."""

    notifier: DesktopNotifier
    error_display_sec: int


@dataclass(frozen=True)
class TrayAction:
    """A menu entry."""

    label: str
    run: Callable[[], None]


def _run_logged(action: TrayAction) -> None:
    logger.info("tray action %r started", action.label)
    try:
        action.run()
    except ACTION_ERRORS:
        logger.exception("tray action %r failed", action.label)
        return
    except Exception:
        # the worker would keep it in a Future nothing reads, so it would vanish
        logger.exception("bug in tray action %r", action.label)
        return
    logger.info("tray action %r finished", action.label)


class Tray(AbstractContextManager["Tray"]):
    """Tray icon, shown until the tray is left; build it on the main thread, then run
    app.exec().

    Left click toggles the target on the GUI thread, as Qt widgets require. Menu actions run one
    at a time on the tray's worker, so a slow one can't freeze the menu.
    """

    def __init__(
        self,
        app: QApplication,
        icon: Path,
        notifications: TrayNotifications | None,
        target: TrayTarget,
        actions: Sequence[TrayAction],
    ) -> None:
        """A left click marks every notification read and opens `target`, or closes it if it is
        open. A right click shows `actions`, then Quit. `app` is the app's QApplication; its name
        is the tooltip. `notifications` is None for an app that sends none; otherwise, while the
        tray is entered, every logger's ERROR records are sent as notifications too."""
        logger.debug("tray for %r with %d actions", app.applicationName(), len(actions))
        self._app: QApplication = app
        # A tray app's windows come and go; only Quit ends it.
        self._app.setQuitOnLastWindowClosed(False)
        self._notifications: TrayNotifications | None = notifications
        # Changed only on the GUI thread, so it needs no lock.
        self._unread: int = 0
        self._worker: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=1)
        self._target: TrayTarget = target
        # None: no notifications, so log records go only to the log.
        self._records: _RecordNotifications | None = (
            None
            if notifications is None
            else _RecordNotifications(self.send, notifications.error_display_sec)
        )
        # Scaled to fit icon_size, up as well as down, so every icon gets the same badge.
        self._plain: QIcon = QIcon(
            QPixmap(str(icon)).scaled(
                CONFIG.tray.icon_size,
                CONFIG.tray.icon_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        # A child of the application, so Qt deletes it with the application.
        self._icon: QSystemTrayIcon = QSystemTrayIcon(QIcon(self._badged(0)), self._app)
        self._icon.setToolTip(app.applicationName())
        menu: QMenu = QMenu()
        for action in actions:
            menu.addAction(action.label, partial(self._submit, action))
        menu.addSeparator()
        menu.addAction("Quit", self._app.quit)

        def clicked(reason: QSystemTrayIcon.ActivationReason) -> None:
            if reason is not QSystemTrayIcon.ActivationReason.Trigger:
                logger.debug("tray activation %s ignored", reason.name)
                return
            self._show_unread(0)
            self._open_or_close()

        self._icon.setContextMenu(menu)
        self._icon.activated.connect(clicked)
        self._icon.show()

    def _open_or_close(self) -> None:
        if self._target.is_open():
            logger.debug("tray click: closing the target")
            self._target.close()
        else:
            logger.debug("tray click: opening the target")
            self._target.open()

    def _submit(self, action: TrayAction) -> None:
        logger.debug("tray action %r queued", action.label)
        self._worker.submit(_run_logged, action)

    @override
    def __enter__(self) -> Self:
        if self._records is not None:
            logging.getLogger().addHandler(self._records)
            logger.debug("ERROR records go to notifications")
        logger.info("tray icon shown")
        return self

    @override
    def __exit__(self, *_: object) -> None:
        if self._records is not None:
            logging.getLogger().removeHandler(self._records)
        # the app may outlive the tray; a left-over icon would call a stopped worker
        self._icon.hide()
        self._worker.shutdown()
        logger.info("tray icon hidden")

    def send(self, title: str, message: str, urgency: Urgency, display_sec: int) -> None:
        """Send a notification, as DesktopNotifier.send does, and count it as unread; from any
        thread, as Qt runs the count on the GUI thread."""
        if self._notifications is None:
            no_notifier: str = "this tray was built without a notifier"
            raise RuntimeError(no_notifier)
        self._notifications.notifier.send(title, message, urgency, display_sec)
        QTimer.singleShot(0, self._app, lambda: self._show_unread(self._unread + 1))

    def _show_unread(self, count: int) -> None:
        logger.debug("unread notifications: %d", count)
        self._unread = count
        self._icon.setIcon(QIcon(self._badged(count)))

    def _badged(self, count: int) -> QPixmap:
        """The icon centred on an icon_size square, with `count` in the badge unless it is 0."""
        pixmap: QPixmap = QPixmap(CONFIG.tray.icon_size, CONFIG.tray.icon_size)
        pixmap.fill(Qt.GlobalColor.transparent)
        with QPainter(pixmap) as painter:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._plain.paint(painter, pixmap.rect())
            if count:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(CONFIG.tray.badge_colour))
                painter.drawEllipse(BADGE_RECT)
                font: QFont = painter.font()
                font.setBold(True)
                font.setPixelSize(CONFIG.tray.badge_text_size)
                painter.setFont(font)
                painter.setPen(QColor(CONFIG.tray.badge_text_colour))
                painter.drawText(BADGE_RECT, Qt.AlignmentFlag.AlignCenter, str(count))
        return pixmap
