"""Web frontend in its own QtWebEngine window. Import before any QApplication exists:
QtWebEngine must load first."""

import logging
from pathlib import Path
from typing import override

from pydantic import HttpUrl
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWebEngineCore import (
    QWebEngineNavigationRequest,
    QWebEngineNewWindowRequest,
    QWebEnginePage,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMainWindow, QWidget

from markcom.config import CONFIG
from markcom.tray import TrayTarget
from markcom.web_scheme import WebScheme

logger: logging.Logger = logging.getLogger(__name__)


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
        if url.scheme() in WebScheme:
            logger.info("Opening %s link to %s in the browser", url.scheme(), url.host())
            if not QDesktopServices.openUrl(url):
                logger.warning(
                    "The desktop could not open a %s link to %s", url.scheme(), url.host()
                )
        else:
            logger.warning("Refused a %s link to %s", url.scheme(), url.host())

    def _on_new_window(self, request: QWebEngineNewWindowRequest) -> None:
        url: QUrl = request.requestedUrl()
        logger.debug("New-window request to %s://%s", url.scheme(), url.host())
        # load() goes through _on_navigation, which filters other sites
        self.load(url)


class WebWindow(TrayTarget):
    """Web page in its own window. Build it after the QApplication; GUI thread only, as Qt
    requires. Closing only hides it, so the page keeps its state, size, and position."""

    def __init__(self, title: str, url: HttpUrl, icon: Path) -> None:
        # view in a holder: closing the view ends its page, closing the holder only hides it
        self._holder: QMainWindow = QMainWindow()
        self._view: QWebEngineView = QWebEngineView()
        self._holder.setCentralWidget(self._view)
        self._start: QUrl = QUrl(str(url))
        self._view.setPage(_OwnOriginPage(self._start, self._holder))
        self._holder.setWindowTitle(title)
        self._holder.setWindowIcon(QIcon(str(icon)))
        self._holder.resize(CONFIG.window.width, CONFIG.window.height)

    @override
    def is_open(self) -> bool:
        return self._holder.isVisible() and not self._holder.isMinimized()

    @override
    def open(self) -> None:
        # page loads on first open, so the app's server may start after this window
        if self._view.url().isEmpty():
            logger.info(
                "Loading %s://%s:%d",
                self._start.scheme(),
                self._start.host(),
                self._start.port(),
            )
            self._view.load(self._start)
        # show() won't un-minimise; showNormal() alone would drop maximised, which Qt keeps
        # while minimised
        if self._holder.isMaximized():
            logger.debug("Showing the window maximised")
            self._holder.showMaximized()
        else:
            logger.debug("Showing the window")
            self._holder.showNormal()

    @override
    def close(self) -> None:
        logger.debug("Hiding the window")
        self._holder.close()
