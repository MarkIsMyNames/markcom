"""The web window's own process, which ends when its stdin does. A fresh window each open also
avoids Wayland showing a re-shown window at the wrong scale, which QtWebEngine stretched."""

import logging
import os
import sys

from PySide6.QtCore import QByteArray, QSettings, QSocketNotifier, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QPalette
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
ORGANISATION: str = "markcom"
GEOMETRY_KEY: str = "geometry"


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
    """The page in a window, at the size the last one saved in `settings`."""

    def __init__(self, spec: WindowSpec, settings: QSettings) -> None:
        super().__init__()
        self._settings: QSettings = settings
        start: QUrl = QUrl(str(spec.url))
        view: QWebEngineView = QWebEngineView(self)
        page: _OwnOriginPage = _OwnOriginPage(start, view)
        # Until the page draws, the theme's colour shows rather than white.
        page.setBackgroundColor(self.palette().color(QPalette.ColorRole.Base))
        view.setPage(page)
        self.setCentralWidget(view)
        self.setWindowTitle(spec.title)
        self.setWindowIcon(QIcon(str(spec.icon)))
        self.resize(CONFIG.window.width, CONFIG.window.height)
        geometry: object = settings.value(GEOMETRY_KEY)
        if isinstance(geometry, QByteArray):
            self.restoreGeometry(geometry)
        logger.info("Loading %s://%s:%d", start.scheme(), start.host(), start.port())
        view.load(start)

    def save_size(self) -> None:
        self._settings.setValue(GEOMETRY_KEY, self.saveGeometry())
        self._settings.sync()


def main() -> None:
    spec: WindowSpec = WindowSpec.model_validate_json(os.environ.pop(SPEC_VARIABLE))
    configure_logging(logging.getLevelName(logging.WARNING))
    app: QApplication = QApplication([spec.title])
    window: OwnOriginWindow = OwnOriginWindow(spec, QSettings(ORGANISATION, spec.title))
    # The app never writes to stdin, so it turns readable only at its end: the app closed the
    # window or ended.
    QSocketNotifier(sys.stdin.fileno(), QSocketNotifier.Type.Read, window).activated.connect(
        window.close
    )
    app.aboutToQuit.connect(window.save_size)
    window.show()
    app.exec()
    logger.info("The window process ends")
