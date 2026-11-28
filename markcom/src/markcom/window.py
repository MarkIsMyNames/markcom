"""Window in own process, so a closed window holds no QtWebEngine memory."""

import json
import logging
import os
import sys
from dataclasses import asdict
from functools import partial
from pathlib import Path
from typing import override

from pydantic import HttpUrl
from PySide6.QtCore import QCoreApplication, QProcess, QProcessEnvironment
from PySide6.QtWidgets import QApplication

from markcom.config import CONFIG
from markcom.tray import TrayTarget
from markcom.window_messages import SPEC_VARIABLE, WindowSpec

logger: logging.Logger = logging.getLogger(__name__)

# -P: working folder can't shadow a module; -c, unlike -m, keeps the module's log name
WINDOW_PROCESS: tuple[str, ...] = ("-P", "-c", "from markcom.window_process import main; main()")


class WebWindow(TrayTarget):
    def __init__(self, title: str, url: HttpUrl, icon: Path) -> None:
        self._url: HttpUrl = url
        self._spec: WindowSpec = WindowSpec(
            title=title,
            url=str(url),
            icon=str(icon),
            width=CONFIG.window.width,
            height=CONFIG.window.height,
        )
        self._process: QProcess | None = None
        app: QCoreApplication | None = QApplication.instance()
        if app is None:
            no_app: str = "build the WebWindow after the QApplication"
            raise RuntimeError(no_app)
        # else Qt kills a running window process at exit
        app.aboutToQuit.connect(self.close)

    @override
    def is_open(self) -> bool:
        return self._process is not None

    @override
    def open(self) -> None:
        if self._process is not None:
            logger.debug("The window is already open")
            return
        # set before start(), which signals a start failure from within
        self._process = self._new_process()
        # scheme, host, port only: URL may carry a token
        logger.info(
            "Starting the window for %s://%s:%s",
            self._url.scheme,
            self._url.host,
            self._url.port,
        )
        self._process.start()

    @override
    def close(self) -> None:
        if self._process is None:
            logger.debug("No window to close")
            return
        logger.debug("Closing the window")
        process: QProcess = self._process
        # end of its stdin closes the window and ends the process
        process.closeWriteChannel()
        process.waitForFinished()

    def _new_process(self) -> QProcess:
        environment: QProcessEnvironment = QProcessEnvironment.systemEnvironment()
        environment.insert(SPEC_VARIABLE, json.dumps(asdict(self._spec)))
        process: QProcess = QProcess()
        process.setProgram(sys.executable)
        process.setArguments(list(WINDOW_PROCESS))
        process.setProcessEnvironment(environment)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.ForwardedChannels)
        process.finished.connect(partial(self._on_finished, process))
        return process

    def _on_finished(self, process: QProcess, exit_code: int, status: QProcess.ExitStatus) -> None:
        if status is QProcess.ExitStatus.NormalExit and exit_code == os.EX_OK:
            logger.info("The window process ended")
        else:
            logger.error("The window process failed: %s, exit code %d", status.name, exit_code)
        self._ended(process)

    def _ended(self, process: QProcess) -> None:
        self._process = None
        process.deleteLater()
        if QApplication.quitOnLastWindowClosed() and not any(
            window.isVisible() for window in QApplication.topLevelWindows()
        ):
            logger.info("The last window closed, so the app quits")
            QApplication.quit()
