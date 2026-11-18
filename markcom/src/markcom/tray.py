"""A system tray icon (Qt): left click runs the app's main action, right click shows its other
actions and Quit. Notifications sent through it count as unread, shown as a badge on the icon,
until the next left click."""

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import override

from desktop_notifier import Urgency
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from markcom.config import CONFIG
from markcom.notifier import DesktopNotifier

logger: logging.Logger = logging.getLogger(__name__)

# What a menu action may fail with (files: OSError, ValueError; browser: OSError; desktop:
# RuntimeError). They are logged so the tray keeps running; anything else is a bug and raises.
ACTION_ERRORS: tuple[type[Exception], ...] = (OSError, ValueError, RuntimeError)
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


def _run_logged(run: Callable[[], None]) -> None:
    try:
        run()
    except ACTION_ERRORS:
        logger.exception("tray action failed")


@dataclass(frozen=True)
class TrayAction:
    """A menu entry."""

    label: str
    run: Callable[[], None]


class Tray(AbstractContextManager["Tray"]):
    """Tray icon; build it and call run() on the main thread.

    Left click toggles the target on the GUI thread, as Qt widgets require. Menu actions run one
    at a time on the tray's worker, so a slow one can't freeze the menu.
    """

    def __init__(
        self,
        app: QApplication,
        icon: Path,
        notifier: DesktopNotifier | None,
        target: TrayTarget,
        actions: Sequence[TrayAction],
    ) -> None:
        """A left click marks every notification read and opens `target`, or closes it if it is
        open. A right click shows `actions`, then Quit. `app` is the app's QApplication; its name
        is the tooltip. `notifier` is None for an app that sends no notifications."""
        self._app: QApplication = app
        # A tray app's windows come and go; only Quit ends it.
        self._app.setQuitOnLastWindowClosed(False)
        self._notifier: DesktopNotifier | None = notifier
        # Changed only on the GUI thread, so it needs no lock.
        self._unread: int = 0
        self._worker: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=1)
        self._target: TrayTarget = target
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
            menu.addAction(action.label, partial(self._submit, action.run))
        menu.addSeparator()
        menu.addAction("Quit", self._app.quit)

        def clicked(reason: QSystemTrayIcon.ActivationReason) -> None:
            if reason is QSystemTrayIcon.ActivationReason.Trigger:
                self._show_unread(0)
                _run_logged(self._open_or_close)

        self._icon.setContextMenu(menu)
        self._icon.activated.connect(clicked)

    def _open_or_close(self) -> None:
        if self._target.is_open():
            logger.debug("tray click: closing the target")
            self._target.close()
        else:
            logger.debug("tray click: opening the target")
            self._target.open()

    def _submit(self, run: Callable[[], None]) -> None:
        self._worker.submit(_run_logged, run)

    @override
    def __exit__(self, *_: object) -> None:
        # the app may outlive the tray; a left-over icon would call a stopped worker
        self._icon.hide()
        self._worker.shutdown()

    def run(self) -> None:
        """Show the icon and block until Quit."""
        self._icon.show()
        self._app.exec()

    def send(self, title: str, message: str, urgency: Urgency, display_sec: int) -> None:
        """Send a notification, as DesktopNotifier.send does, and count it as unread; from any
        thread, as Qt runs the count on the GUI thread."""
        if self._notifier is None:
            no_notifier: str = "this tray was built without a notifier"
            raise RuntimeError(no_notifier)
        self._notifier.send(title, message, urgency, display_sec)
        QTimer.singleShot(0, self._app, lambda: self._show_unread(self._unread + 1))

    def _show_unread(self, count: int) -> None:
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
