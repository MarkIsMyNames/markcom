"""A local web frontend shown in its own QtWebEngine window. Import this module before the
QApplication is created: QtWebEngine must be loaded first."""

import logging
from collections.abc import Callable
from concurrent.futures import Future
from pathlib import Path
from typing import Self, override

from pydantic import HttpUrl
from PySide6.QtCore import QCoreApplication, Qt, QThread, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWebEngineCore import (
    QWebEngineNavigationRequest,
    QWebEngineNewWindowRequest,
    QWebEnginePage,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from markcom.config import CONFIG
from markcom.tray import TrayTarget

logger: logging.Logger = logging.getLogger(__name__)


def _on_gui_thread[T](work: Callable[[], T]) -> T:
    """Run `work` on the main thread and return its result, or raise what it raised."""
    app: QCoreApplication | None = QApplication.instance()
    if app is None or not isinstance(app, QApplication):
        # Qt aborts the whole process if a widget is built with no application.
        no_app: str = "no QApplication: use a WebWindow under a Tray or run_without_tray"
        raise RuntimeError(no_app)
    if QThread.isMainThread():
        return work()
    result: Future[T] = Future()

    def run() -> None:
        try:
            result.set_result(work())
        except BaseException as error:
            result.set_exception(error)
            # The caller gets the error through the Future; re-raising also reports it on the
            # GUI thread.
            raise

    QTimer.singleShot(0, app, run)
    return result.result(timeout=CONFIG.window.gui_wait_sec)


WEB_SCHEMES: frozenset[str] = frozenset({"http", "https"})


class _OwnOriginPage(QWebEnginePage):
    """A page that stays on one origin: other web links go to the default browser."""

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
        # Scheme and host only: a URL can carry a token.
        if url.scheme() in WEB_SCHEMES:
            logger.info("Opening %s link to %s in the browser", url.scheme(), url.host())
            QDesktopServices.openUrl(url)
        else:
            logger.warning("Refused a %s link to %s", url.scheme(), url.host())

    def _on_new_window(self, request: QWebEngineNewWindowRequest) -> None:
        url: QUrl = request.requestedUrl()
        if self._is_own_origin(url):
            self.load(url)
        else:
            self._send_away(url)


class WebWindow(TrayTarget):
    """A web page in its own window. The window is built on the first open() and then only
    hidden, so the page keeps its state, size and position. Methods work from any thread."""

    def __init__(self, title: str, url: HttpUrl, icon: Path) -> None:
        self._title: str = title
        self._url: HttpUrl = url
        self._icon: Path = icon
        # None until the first open(): a widget cannot exist before the QApplication, which
        # Tray or run_without_tray creates after this object.
        self._holder: QWidget | None = None

    @override
    def is_open(self) -> bool:
        return _on_gui_thread(self._is_visible)

    @override
    def open(self) -> None:
        _on_gui_thread(self._show)

    @override
    def close(self) -> None:
        _on_gui_thread(self._hide)

    def _is_visible(self) -> bool:
        return (
            self._holder is not None and self._holder.isVisible() and not self._holder.isMinimized()
        )

    def _show(self) -> None:
        if self._holder is None:
            self._holder = self._build()
        self._holder.setWindowState(self._holder.windowState() & ~Qt.WindowState.WindowMinimized)
        self._holder.show()
        self._holder.raise_()
        self._holder.activateWindow()

    def _hide(self) -> None:
        if self._holder is not None:
            self._holder.close()

    def _build(self) -> QWidget:
        # The view sits in a holder: closing a view itself ends its page, closing the holder
        # only hides it.
        holder: QWidget = QWidget()
        layout: QVBoxLayout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        view: QWebEngineView = QWebEngineView(holder)
        layout.addWidget(view)
        start: QUrl = QUrl(str(self._url))
        view.setPage(_OwnOriginPage(start, holder))
        view.load(start)
        holder.setWindowTitle(self._title)
        holder.setWindowIcon(QIcon(str(self._icon)))
        holder.resize(CONFIG.window.width, CONFIG.window.height)
        return holder


class _Application(QApplication):
    """A QApplication that shuts down when its `with` block ends, as Qt allows only one at a
    time."""

    def __init__(self, name: str) -> None:
        super().__init__([name])

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.shutdown()


def run_without_tray(name: str, window: WebWindow) -> None:
    """Run `window` as an app with no tray, on the main thread: open it and block until it is
    closed."""
    # Qt's default stays on: with no tray, closing the last window must end the app.
    with _Application(name) as app:
        window.open()
        app.exec()
