"""A local web frontend shown in its own QtWebEngine window. Import this module before the
QApplication is created: QtWebEngine must be loaded first."""

import logging
from collections.abc import Callable
from concurrent.futures import Future
from pathlib import Path
from typing import override

from pydantic import HttpUrl
from PySide6.QtCore import QThread, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from markcom.config import CONFIG
from markcom.tray import TrayTarget

logger: logging.Logger = logging.getLogger(__name__)


def _on_gui_thread[T](work: Callable[[], T]) -> T:
    """Run `work` on the main thread and return its result, or raise what it raised."""
    app: QApplication | None = None
    instance = QApplication.instance()
    if isinstance(instance, QApplication):
        app = instance
    if app is None:
        # Qt aborts the whole process if a widget is built with no application.
        no_app: str = "no QApplication: build a Tray or a WindowApp before using a WebWindow"
        raise RuntimeError(no_app)
    if QThread.isMainThread():
        return work()
    result: Future[T] = Future()

    def run() -> None:
        try:
            result.set_result(work())
        except BaseException as error:
            result.set_exception(error)
            raise

    QTimer.singleShot(0, app, run)
    return result.result()


class WebWindow(TrayTarget):
    """A web page in its own window. The window is built on the first open() and then only
    hidden, so the page keeps its state, size and position. Methods work from any thread."""

    def __init__(self, title: str, url: HttpUrl, icon: Path) -> None:
        self._title: str = title
        self._url: HttpUrl = url
        self._icon: Path = icon
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
        return self._holder is not None and self._holder.isVisible()

    def _show(self) -> None:
        if self._holder is None:
            self._holder = self._build()
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
        view.load(str(self._url))
        holder.setWindowTitle(self._title)
        holder.setWindowIcon(QIcon(str(self._icon)))
        holder.resize(CONFIG.window.width, CONFIG.window.height)
        return holder
