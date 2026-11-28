"""Own process, fresh each open: Wayland shows a re-shown window at wrong scale."""

import logging
import os
import sys

from PySide6.QtCore import QByteArray, QSettings, QSocketNotifier, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QPalette
from PySide6.QtWebEngineCore import (
    QWebEngineNavigationRequest,
    QWebEngineNewWindowRequest,
    QWebEnginePage,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget

from markcom.web_scheme import WebProtocol
from markcom.window_messages import SPEC_VARIABLE, WindowSpec

logger: logging.Logger = logging.getLogger(__name__)

BROWSER_SCHEMES: frozenset[WebProtocol] = frozenset({WebProtocol.HTTP, WebProtocol.HTTPS})
ORGANISATION: str = "markcom"
GEOMETRY_KEY: str = "geometry"


class _OwnOriginPage(QWebEnginePage):
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
            # openUrl returns False, never raises, so only this shows a failure
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
    def __init__(self, spec: WindowSpec, settings: QSettings) -> None:
        super().__init__()
        self._settings: QSettings = settings
        start: QUrl = QUrl(spec.url)
        view: QWebEngineView = QWebEngineView(self)
        page: _OwnOriginPage = _OwnOriginPage(start, view)
        # theme colour, not white, until the page draws
        page.setBackgroundColor(self.palette().color(QPalette.ColorRole.Base))
        view.setPage(page)
        self.setCentralWidget(view)
        self.setWindowTitle(spec.title)
        self.setWindowIcon(QIcon(spec.icon))
        self.resize(spec.width, spec.height)
        geometry: object = settings.value(GEOMETRY_KEY)
        if isinstance(geometry, QByteArray):
            self.restoreGeometry(geometry)
        # hidden until loaded so a click never shows an empty window; failed load shows too
        view.loadFinished.connect(self.show, Qt.ConnectionType.SingleShotConnection)
        logger.info("Loading %s://%s:%d", start.scheme(), start.host(), start.port())
        view.load(start)

    def save_size(self) -> None:
        self._settings.setValue(GEOMETRY_KEY, self.saveGeometry())
        self._settings.sync()


def main() -> None:
    spec: WindowSpec = WindowSpec.from_json(os.environ.pop(SPEC_VARIABLE))
    app: QApplication = QApplication([spec.title])
    window: OwnOriginWindow = OwnOriginWindow(spec, QSettings(ORGANISATION, spec.title))
    # app never writes stdin: readable only at its end, so window closed or app ended
    # quit, not close: a window hidden while loading wouldn't quit on close
    QSocketNotifier(sys.stdin.fileno(), QSocketNotifier.Type.Read, window).activated.connect(
        app.quit
    )
    app.aboutToQuit.connect(window.save_size)
    app.exec()
    logger.info("The window process ends")
