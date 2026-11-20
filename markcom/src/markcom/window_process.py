"""The web window's own process, which markcom.window.WebWindow starts on each open by calling
main(), with a WindowSpec in the environment. Its window closes when its stdin does, and the
process ends with it, so a closed window holds none of QtWebEngine's memory.

Each open is a new window, so the page always loads at the window's settled size and scale. A
hidden window shown again starts at the screen's whole-number scale on Wayland, and QtWebEngine
stretches the frame drawn at that scale over the window until the next frame."""

import logging
import os
import sys
from collections.abc import Callable
from functools import partial
from io import FileIO
from typing import override

from PySide6.QtCore import QByteArray, QEvent, QObject, QSocketNotifier, QUrl
from PySide6.QtGui import (
    QCloseEvent,
    QDesktopServices,
    QIcon,
    QMoveEvent,
    QPalette,
    QResizeEvent,
)
from PySide6.QtWebEngineCore import (
    QWebEngineNavigationRequest,
    QWebEngineNewWindowRequest,
    QWebEnginePage,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget

from markcom.config import CONFIG
from markcom.logs import configure_logging
from markcom.web_scheme import WebProtocol
from markcom.window_messages import LINE_END, SHOW, SPEC_VARIABLE, WindowReport, WindowSpec

logger: logging.Logger = logging.getLogger(__name__)

# Links that leave the window for the default browser; any other scheme is refused.
BROWSER_SCHEMES: frozenset[WebProtocol] = frozenset({WebProtocol.HTTP, WebProtocol.HTTPS})
# Bytes read from stdin at a time; a command is a few.
READ_SIZE: int = 4096

type Report = Callable[[WindowReport], None]


class _OwnOriginPage(QWebEnginePage):
    """No address bar or Back button, so other sites open in the default browser."""

    def __init__(self, origin: QUrl, parent: QWidget) -> None:
        super().__init__(parent)
        self._origin: QUrl = origin
        self.navigationRequested.connect(self._on_navigation)
        self.newWindowRequested.connect(self._on_new_window)

    def _on_navigation(self, request: QWebEngineNavigationRequest) -> None:
        url: QUrl = request.url()
        logger.debug(
            "Navigation to %s://%s, main frame %s", url.scheme(), url.host(), request.isMainFrame()
        )
        if request.isMainFrame() and not self._is_own_origin(url):
            request.reject()
            self._send_away(url)

    def _is_own_origin(self, url: QUrl) -> bool:
        return (
            url.scheme() == self._origin.scheme()
            and url.host() == self._origin.host()
            and url.port() == self._origin.port()
        )

    @staticmethod
    def _send_away(url: QUrl) -> None:
        # scheme and host only: URL may carry a token
        if url.scheme() in BROWSER_SCHEMES:
            logger.info("Opening %s link to %s in the browser", url.scheme(), url.host())
            if not QDesktopServices.openUrl(url):
                logger.error("The desktop could not open a %s link to %s", url.scheme(), url.host())
        else:
            logger.warning("Refused a %s link to %s", url.scheme(), url.host())

    def _on_new_window(self, request: QWebEngineNewWindowRequest) -> None:
        url: QUrl = request.requestedUrl()
        logger.debug("New-window request to %s://%s", url.scheme(), url.host())
        # load() goes through _on_navigation, which filters other sites
        self.load(url)


class OwnOriginWindow(QMainWindow):
    """The page in a window, loading as it is built. Reports each minimise, bring-back and
    close, so the app knows its state and the next window can take its size."""

    def __init__(self, spec: WindowSpec, report: Report) -> None:
        super().__init__()
        self._report: Report = report
        start: QUrl = QUrl(str(spec.url))
        view: QWebEngineView = QWebEngineView(self)
        page: _OwnOriginPage = _OwnOriginPage(start, view)
        # until the page draws: the theme's content colour, not white, so a dark page won't flash
        page.setBackgroundColor(self.palette().color(QPalette.ColorRole.Base))
        view.setPage(page)
        self.setCentralWidget(view)
        self.setWindowTitle(spec.title)
        self.setWindowIcon(QIcon(str(spec.icon)))
        if spec.geometry is None:
            logger.debug("First window, so the configured size")
            self.resize(CONFIG.window.width, CONFIG.window.height)
        else:
            logger.debug("The last window's size and state")
            self.restoreGeometry(QByteArray(spec.geometry))
        logger.info("Loading %s://%s:%d", start.scheme(), start.host(), start.port())
        view.load(start)

    def bring_back(self) -> None:
        # show() won't un-minimise; showNormal() alone would drop maximised, which Qt keeps
        # while minimised
        if self.isMaximized():
            logger.debug("Showing the window maximised")
            self.showMaximized()
        else:
            logger.debug("Showing the window")
            self.showNormal()

    @override
    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._send_report()

    # Each resize and move is reported, so a window opened just after this one closes, before its
    # last report arrives, still takes its size.
    @override
    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._send_report()

    @override
    def moveEvent(self, event: QMoveEvent) -> None:
        super().moveEvent(event)
        self._send_report()

    @override
    def closeEvent(self, event: QCloseEvent) -> None:
        logger.debug("Closing the window")
        self._send_report()
        super().closeEvent(event)

    def _send_report(self) -> None:
        self._report(
            WindowReport(minimised=self.isMinimized(), geometry=bytes(self.saveGeometry().data()))
        )


class AppCommands(QObject):
    """The app's commands, read from `fd` (stdin): SHOW brings the window back; the end of input
    closes it. A child of the window, so it lives as long as the window does."""

    def __init__(self, fd: int, window: OwnOriginWindow) -> None:
        super().__init__(window)
        self._fd: int = fd
        self._window: OwnOriginWindow = window
        # A command's start, until the rest of its line arrives.
        self._partial: bytes = b""
        self._notifier: QSocketNotifier = QSocketNotifier(fd, QSocketNotifier.Type.Read, self)
        self._notifier.activated.connect(self._read)

    def _read(self) -> None:
        chunk: bytes = os.read(self._fd, READ_SIZE)
        if not chunk:
            logger.info("The app closed the window")
            self._notifier.setEnabled(False)
            self._window.close()
            return
        lines: list[bytes] = (self._partial + chunk).split(LINE_END)
        self._partial = lines.pop()
        for line in lines:
            if line == SHOW:
                self._window.bring_back()
            else:
                logger.warning("Ignored an unknown command of %d bytes from the app", len(line))


def _write_report(reports: FileIO, report: WindowReport) -> None:
    try:
        # one unbuffered write, so a report never interleaves with another
        reports.write(report.model_dump_json().encode() + LINE_END)
    except BrokenPipeError:
        # the app has gone, so nothing reads reports; its closed stdin ends this process too
        logger.debug("The app has gone, so the report was not sent")


def main() -> None:
    """The window process: show the spec's page until stdin closes or the window does."""
    spec: WindowSpec = WindowSpec.model_validate_json(os.environ.pop(SPEC_VARIABLE))
    configure_logging(spec.log_level)
    # Reports get a copy of stdout that QtWebEngine's helper processes don't inherit, and stdout
    # itself goes to stderr, so no other output can pass for a report.
    with os.fdopen(os.dup(sys.stdout.fileno()), "wb", buffering=0) as reports:
        os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
        app: QApplication = QApplication([spec.title])
        window: OwnOriginWindow = OwnOriginWindow(spec, partial(_write_report, reports))
        AppCommands(sys.stdin.fileno(), window)
        window.bring_back()
        app.exec()
    logger.info("The window process ends")
