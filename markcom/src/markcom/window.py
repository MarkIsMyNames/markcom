"""Web frontend in its own window, run by its own process (markcom.window_process), started on each
open and ended on each close, so a closed window holds no QtWebEngine memory."""

import logging
import sys
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

# -P: app's working folder can't shadow a module; -c, not -m, so the module logs under its name
WINDOW_PROCESS: tuple[str, ...] = ("-P", "-c", "from markcom.window_process import main; main()")
MS_PER_SEC: int = 1000


class WebWindow(TrayTarget):
    """Web page in its own window. Build it after the QApplication; GUI thread only, as Qt
    requires. Each open loads the page afresh, at the last window's size."""

    def __init__(self, title: str, url: HttpUrl, icon: Path) -> None:
        self._spec: WindowSpec = WindowSpec(
            title=title,
            url=url,
            icon=icon,
            log_level=logging.getLevelName(logging.getLogger().getEffectiveLevel()),
        )
        # None: no window open
        self._process: QProcess | None = None
        # deleting a QProcess kills its process, so closed ones are kept until they end
        self._ending: set[QProcess] = set()
        app: QCoreApplication | None = QApplication.instance()
        if app is None:
            no_app: str = "build the WebWindow after the QApplication"
            raise RuntimeError(no_app)
        # else Qt kills a running window process at exit
        app.aboutToQuit.connect(self._end_on_quit)

    @override
    def is_open(self) -> bool:
        return self._process is not None

    @override
    def open(self) -> None:
        if self._process is not None:
            logger.debug("The window is already open")
            return
        # set before start(): a failure to start is signalled within it
        self._process = self._new_process()
        # scheme, host and port only: URL may carry a token
        logger.info(
            "Starting the window for %s://%s:%s",
            self._spec.url.scheme,
            self._spec.url.host,
            self._spec.url.port,
        )
        self._process.start()

    @override
    def close(self) -> None:
        if self._process is None:
            logger.debug("No window to close")
            return
        logger.debug("Closing the window")
        self._ending.add(self._process)
        # end of input closes the window, and its process ends
        self._process.closeWriteChannel()
        self._process = None

    def _new_process(self) -> QProcess:
        environment: QProcessEnvironment = QProcessEnvironment.systemEnvironment()
        environment.insert(SPEC_VARIABLE, self._spec.model_dump_json())
        process: QProcess = QProcess()
        process.setProgram(sys.executable)
        process.setArguments(list(WINDOW_PROCESS))
        process.setProcessEnvironment(environment)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.ForwardedChannels)
        process.finished.connect(partial(self._on_finished, process))
        process.errorOccurred.connect(partial(self._on_error, process))
        return process

    def _on_finished(self, process: QProcess, exit_code: int, status: QProcess.ExitStatus) -> None:
        if status is QProcess.ExitStatus.NormalExit and exit_code == 0:
            logger.info("The window process ended")
        else:
            logger.error("The window process failed: %s, exit code %d", status.name, exit_code)
        self._ended(process)

    def _on_error(self, process: QProcess, error: QProcess.ProcessError) -> None:
        if error is QProcess.ProcessError.FailedToStart:
            # no process, so no finished signal follows
            logger.error("The window process failed to start: %s", process.errorString())
            self._ended(process)
            return
        logger.warning("The window process reported %s: %s", error.name, process.errorString())

    def _ended(self, process: QProcess) -> None:
        self._ending.discard(process)
        # closed from its title bar, or failed
        if process is self._process:
            self._process = None
        process.deleteLater()
        # as Qt does for its own windows: no tray, last window closed, app quits
        if (
            QApplication.quitOnLastWindowClosed()
            and self._process is None
            and not self._ending
            and not any(window.isVisible() for window in QApplication.topLevelWindows())
        ):
            logger.info("The last window closed, so the app quits")
            QApplication.quit()

    def _end_on_quit(self) -> None:
        self.close()
        for process in tuple(self._ending):
            if not process.waitForFinished(int(CONFIG.window.close_wait_sec * MS_PER_SEC)):
                logger.warning(
                    "The window process did not end within %s s, so Qt kills it",
                    CONFIG.window.close_wait_sec,
                )
