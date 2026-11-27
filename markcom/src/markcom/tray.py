import logging
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
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
from markcom.notifier import NEVER_EXPIRES_SEC, NOTIFIER_THREAD, DesktopNotifier

logger: logging.Logger = logging.getLogger(__name__)

# bad log call args (TypeError, ValueError, KeyError) or deleted Qt object (RuntimeError)
NOTIFY_ERRORS: tuple[type[Exception], ...] = (TypeError, ValueError, KeyError, RuntimeError)
BADGE_RECT: QRectF = QRectF(
    CONFIG.tray.icon_size - CONFIG.tray.badge_size - CONFIG.tray.badge_margin,
    CONFIG.tray.icon_size - CONFIG.tray.badge_size - CONFIG.tray.badge_margin,
    CONFIG.tray.badge_size,
    CONFIG.tray.badge_size,
)


class TrayTarget(ABC):
    # GUI thread calls these: return fast, slow work to own worker
    # app may toggle outside the tray, so is_open reports real state, not last click
    @abstractmethod
    def is_open(self) -> bool: ...

    # open/close return only once is_open() reflects it, or next click toggles wrong
    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...


type Send = Callable[[str, str, Urgency, int], None]


class _RecordNotifications(logging.Handler):
    def __init__(self, send: Send, error_display_sec: int) -> None:
        super().__init__(logging.ERROR)
        self._send: Send = send
        self._error_display_sec: int = error_display_sec

    @override
    def filter(self, record: logging.LogRecord) -> bool | logging.LogRecord:
        # notifier thread logs while a send waits holding this lock: sending it deadlocks
        return record.threadName != NOTIFIER_THREAD and super().filter(record)

    @override
    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._notify(record)
        except NOTIFY_ERRORS:
            # handler must not raise into the log call; handleError reports on stderr
            self.handleError(record)

    def _notify(self, record: logging.LogRecord) -> None:
        title: str = record.levelname.capitalize()
        body: str = record.getMessage()
        error: BaseException | None
        _, error, _ = record.exc_info or (None, None, None)
        if error is not None:
            # traceback only in log; notification says only why
            body = f"{body}: {''.join(format_exception_only(error, show_group=True)).strip()}"
        if record.levelno >= logging.CRITICAL:
            self._send(title, body, Urgency.Critical, NEVER_EXPIRES_SEC)
            return
        # not critical: desktops keep critical ones until dismissed, ignoring display_sec
        self._send(title, body, Urgency.Normal, self._error_display_sec)


@dataclass(frozen=True)
class TrayNotifications:
    notifier: DesktopNotifier
    error_display_sec: int


@dataclass(frozen=True)
class TrayAction:
    label: str
    run: Callable[[], None]


def _run_logged(action: TrayAction) -> None:
    logger.info("tray action %r started", action.label)
    try:
        action.run()
    except Exception:
        # raised, it'd sit unread in a Future
        logger.exception("tray action %r failed", action.label)
        return
    logger.info("tray action %r finished", action.label)


class Tray:
    def __init__(
        self,
        app: QApplication,
        icon: Path,
        notifications: TrayNotifications | None,
        target: TrayTarget,
        actions: Sequence[TrayAction],
    ) -> None:
        logger.debug("tray for %r with %d actions", app.applicationName(), len(actions))
        self._app: QApplication = app
        # windows come and go; only Quit ends a tray app
        self._app.setQuitOnLastWindowClosed(False)
        self._notifications: TrayNotifications | None = notifications
        # GUI thread only, so no lock
        self._unread: int = 0
        # one worker: a slow menu action can't freeze the menu
        self._worker: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=1)
        self._target: TrayTarget = target
        self._records: _RecordNotifications | None = (
            None
            if notifications is None
            else _RecordNotifications(self.send, notifications.error_display_sec)
        )
        # scaled up too, so every icon gets the same badge
        self._plain: QIcon = QIcon(
            QPixmap(str(icon)).scaled(
                CONFIG.tray.icon_size,
                CONFIG.tray.icon_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        # child of the app, so Qt deletes it with the app
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

    def __enter__(self) -> Self:
        if self._records is not None:
            logging.getLogger().addHandler(self._records)
            logger.debug("ERROR records go to notifications")
        logger.info("tray icon shown")
        return self

    def __exit__(self, *_: object) -> None:
        if self._records is not None:
            logging.getLogger().removeHandler(self._records)
        # app may outlive tray; left-over icon would call a stopped worker
        self._icon.hide()
        self._worker.shutdown()
        logger.info("tray icon hidden")

    def send(self, title: str, message: str, urgency: Urgency, display_sec: int) -> None:
        # any thread: Qt runs the unread count on the GUI thread
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
