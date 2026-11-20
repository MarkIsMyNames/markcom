"""The web window's own process: WebWindow starts it on each open, with a WindowSpec in its
environment, and it ends when its stdin closes, so a closed window holds no QtWebEngine memory.
A fresh window each open also avoids Wayland's re-shown window starting at the wrong scale, which
QtWebEngine showed as a stretched frame."""

import logging
import os
import sys
from typing import override

from PySide6.QtCore import QByteArray, QObject, QSettings, QSocketNotifier, QUrl
from PySide6.QtGui import QCloseEvent, QDesktopServices, QIcon, QPalette
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
from markcom.window_messages import SPEC_VARIABLE, WindowSpec

logger: logging.Logger = logging.getLogger(__name__)

# Links that leave the window for the default browser; any other scheme is refused.
BROWSER_SCHEMES: frozenset[WebProtocol] = frozenset({WebProtocol.HTTP, WebProtocol.HTTPS})
# The window's size and maximised state, kept in ~/.config/<ORGANISATION>/<title>.conf.
ORGANISATION: str = "markcom"
GEOMETRY_KEY: str = "geometry"
READ_SIZE: int = 4096


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
    """The page in a window, loading as it is built, at the size `settings` kept from the last
    one."""

    def __init__(self, spec: WindowSpec, settings: QSettings) -> None:
        super().__init__()
        self._settings: QSettings = settings
        start: QUrl = QUrl(str(spec.url))
        view: QWebEngineView = QWebEngineView(self)
        page: _OwnOriginPage = _OwnOriginPage(start, view)
        # theme colour until page draws: dark page won't flash white
        page.setBackgroundColor(self.palette().color(QPalette.ColorRole.Base))
        view.setPage(page)
        self.setCentralWidget(view)
        self.setWindowTitle(spec.title)
        self.setWindowIcon(QIcon(str(spec.icon)))
        geometry: object = settings.value(GEOMETRY_KEY)
        if isinstance(geometry, QByteArray):
            self.restoreGeometry(geometry)
        else:
            logger.debug("No saved size, so the configured one")
            self.resize(CONFIG.window.width, CONFIG.window.height)
        logger.info("Loading %s://%s:%d", start.scheme(), start.host(), start.port())
        view.load(start)

    @override
    def closeEvent(self, event: QCloseEvent) -> None:
        self._settings.setValue(GEOMETRY_KEY, self.saveGeometry())
        self._settings.sync()
        super().closeEvent(event)


class CloseOnEndOfInput(QObject):
    """Closes the window when `fd` (stdin) reaches its end: the app closed it, or the app ended.
    A child of the window, so it lives as long as the window does."""

    def __init__(self, fd: int, window: QMainWindow) -> None:
        super().__init__(window)
        self._fd: int = fd
        self._window: QMainWindow = window
        self._notifier: QSocketNotifier = QSocketNotifier(fd, QSocketNotifier.Type.Read, self)
        self._notifier.activated.connect(self._read)

    def _read(self) -> None:
        if os.read(self._fd, READ_SIZE):
            return
        logger.info("The app closed the window")
        self._notifier.setEnabled(False)
        self._window.close()


def main() -> None:
    spec: WindowSpec = WindowSpec.model_validate_json(os.environ.pop(SPEC_VARIABLE))
    configure_logging(spec.log_level)
    app: QApplication = QApplication([spec.title])
    window: OwnOriginWindow = OwnOriginWindow(spec, QSettings(ORGANISATION, spec.title))
    CloseOnEndOfInput(sys.stdin.fileno(), window)
    window.show()
    app.exec()
    logger.info("The window process ends")
