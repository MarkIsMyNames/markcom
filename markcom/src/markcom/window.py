"""Web frontend in its own QtWebEngine window. Import before any QApplication exists:
QtWebEngine must load first."""

import logging
from pathlib import Path
from typing import Self, override

from pydantic import HttpUrl
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWebEngineCore import (
    QWebEngineNavigationRequest,
    QWebEngineNewWindowRequest,
    QWebEnginePage,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget

from markcom.config import CONFIG
from markcom.tray import TrayTarget

logger: logging.Logger = logging.getLogger(__name__)


WEB_SCHEMES: frozenset[str] = frozenset({"http", "https"})


class _OwnOriginPage(QWebEnginePage):
    """No address bar or Back button, so other sites open in the default browser."""

    def __init__(self, origin: QUrl, parent: QWidget) -> None:
        super().__init__(parent)
        self._origin: QUrl = origin
        self.navigationRequested.connect(self._on_navigation)
        self.newWindowRequested.connect(self._on_new_window)

    def _on_navigation(self, request: QWebEngineNavigationRequest) -> None:
        url: QUrl = request.url()
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
        if url.scheme() in WEB_SCHEMES:
            logger.info("Opening %s link to %s in the browser", url.scheme(), url.host())
            QDesktopServices.openUrl(url)
        else:
            logger.warning("Refused a %s link to %s", url.scheme(), url.host())

    def _on_new_window(self, request: QWebEngineNewWindowRequest) -> None:
        # load() goes through _on_navigation, which filters other sites
        self.load(request.requestedUrl())


class WebWindow(TrayTarget):
    """Web page in its own window. Only hidden after the first open(), so the page keeps its
    state, size, and position. GUI thread only, as Qt requires."""

    def __init__(self, title: str, url: HttpUrl, icon: Path) -> None:
        self._title: str = title
        self._url: HttpUrl = url
        self._icon: Path = icon
        # None until first open(): widgets need the QApplication, which Tray or Application
        # creates after this
        self._holder: QMainWindow | None = None

    @override
    def is_open(self) -> bool:
        return (
            self._holder is not None and self._holder.isVisible() and not self._holder.isMinimized()
        )

    @override
    def open(self) -> None:
        if self._holder is None:
            self._holder = self._build()
        # show() won't un-minimise; showNormal() alone would drop maximised, which Qt keeps
        # while minimised
        if self._holder.isMaximized():
            self._holder.showMaximized()
        else:
            self._holder.showNormal()

    @override
    def close(self) -> None:
        if self._holder is not None:
            self._holder.close()

    def _build(self) -> QMainWindow:
        # view in a holder: closing the view ends its page, closing the holder only hides it
        holder: QMainWindow = QMainWindow()
        view: QWebEngineView = QWebEngineView()
        holder.setCentralWidget(view)
        start: QUrl = QUrl(str(self._url))
        view.setPage(_OwnOriginPage(start, holder))
        view.load(start)
        holder.setWindowTitle(self._title)
        holder.setWindowIcon(QIcon(str(self._icon)))
        holder.resize(CONFIG.window.width, CONFIG.window.height)
        return holder


class Application(QApplication):
    """Qt application for an app with no tray; exec() on the main thread.

    `with` shuts it down: Qt allows one at a time. Closing the last window quits (Qt default);
    Tray turns that off, so there a close only hides.
    """

    def __init__(self, name: str) -> None:
        super().__init__([name])

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.shutdown()
