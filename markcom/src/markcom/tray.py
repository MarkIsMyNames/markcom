"""A system tray icon (Qt): left click runs the app's main action, right click shows its other
actions and Quit. Notifications sent through it count as unread, shown as a badge on the icon,
until the next left click."""

import logging
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

from markcom.notifier import DesktopNotifier

logger: logging.Logger = logging.getLogger(__name__)

# What a menu action may fail with (files: OSError, ValueError; browser: OSError; desktop:
# RuntimeError). They are logged so the tray keeps running; anything else is a bug and raises.
ACTION_ERRORS: tuple[type[Exception], ...] = (OSError, ValueError, RuntimeError)
# Edge in pixels of the icon the badge is drawn on; the desktop scales it to the panel.
ICON_SIZE: int = 64
# The badge's edge in pixels, in the icon's bottom-right corner, as messaging apps draw theirs.
BADGE_SIZE: int = 28
# Its count's height in pixels.
BADGE_TEXT_SIZE: int = 20
# Where the badge is drawn, leaving 3 pixels to the icon's edge so the panel does not clip it.
BADGE_RECT: QRectF = QRectF(
    ICON_SIZE - BADGE_SIZE - 3, ICON_SIZE - BADGE_SIZE - 3, BADGE_SIZE, BADGE_SIZE
)
BADGE_COLOUR: QColor = QColor("#d32f2f")
BADGE_TEXT_COLOUR: QColor = QColor("#ffffff")


@dataclass(frozen=True)
class TrayAction:
    """A menu entry."""

    label: str
    run: Callable[[], None]


class Tray(AbstractContextManager["Tray"]):
    """Tray icon; build it and call run() on the main thread.

    The click and the menu's actions run one at a time on the tray's own worker, so a slow one
    cannot freeze the menu.
    """

    def __init__(
        self,
        name: str,
        icon: Path,
        notifier: DesktopNotifier | None,
        on_click: Callable[[], None],
        actions: Sequence[TrayAction],
    ) -> None:
        """A left click marks every notification read and runs `on_click`; a right click shows
        `actions`, then Quit. `notifier` is None for an app that sends no notifications."""
        self._app: QApplication = QApplication([name])
        self._notifier: DesktopNotifier | None = notifier
        # Changed only on the GUI thread, so it needs no lock.
        self._unread: int = 0
        self._worker: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=1)
        # Scaled to fit ICON_SIZE, up as well as down, so every icon gets the same badge.
        self._plain: QIcon = QIcon(
            QPixmap(str(icon)).scaled(
                ICON_SIZE,
                ICON_SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        # A child of the application, so Qt deletes it with the application.
        self._icon: QSystemTrayIcon = QSystemTrayIcon(QIcon(self._badged(0)), self._app)
        self._icon.setToolTip(name)
        menu: QMenu = QMenu()
        for action in actions:
            menu.addAction(action.label, partial(self._submit, action.run))
        menu.addSeparator()
        menu.addAction("Quit", self._app.quit)

        def clicked(reason: QSystemTrayIcon.ActivationReason) -> None:
            if reason is QSystemTrayIcon.ActivationReason.Trigger:
                self._show_unread(0)
                self._submit(on_click)

        self._icon.setContextMenu(menu)
        self._icon.activated.connect(clicked)

    def _submit(self, run: Callable[[], None]) -> None:
        def guarded() -> None:
            try:
                run()
            except ACTION_ERRORS:
                logger.exception("tray action failed")

        self._worker.submit(guarded)

    @override
    def __exit__(self, *_: object) -> None:
        self._worker.shutdown()
        # Release the application, as Qt allows only one at a time.
        self._app.shutdown()

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
        """The icon centred on an ICON_SIZE square, with `count` in the badge unless it is 0."""
        pixmap: QPixmap = QPixmap(ICON_SIZE, ICON_SIZE)
        pixmap.fill(Qt.GlobalColor.transparent)
        with QPainter(pixmap) as painter:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._plain.paint(painter, pixmap.rect())
            if count:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(BADGE_COLOUR)
                painter.drawEllipse(BADGE_RECT)
                font: QFont = painter.font()
                font.setBold(True)
                font.setPixelSize(BADGE_TEXT_SIZE)
                painter.setFont(font)
                painter.setPen(BADGE_TEXT_COLOUR)
                painter.drawText(BADGE_RECT, Qt.AlignmentFlag.AlignCenter, str(count))
        return pixmap
