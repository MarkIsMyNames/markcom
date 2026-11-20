"""Web frontend in its own window, run by its own process (markcom.window_process). The process
starts on each open and ends on each close, so a closed window holds none of QtWebEngine's
memory, and the app's process never loads QtWebEngine at all."""

import logging
import sys
from functools import partial
from pathlib import Path
from typing import override

from pydantic import HttpUrl, ValidationError
from PySide6.QtCore import QCoreApplication, QProcess, QProcessEnvironment
from PySide6.QtWidgets import QApplication

from markcom.config import CONFIG
from markcom.tray import TrayTarget
from markcom.window_messages import LINE_END, SHOW, SPEC_VARIABLE, WindowReport, WindowSpec

logger: logging.Logger = logging.getLogger(__name__)

# -P: the app's working folder can't shadow a module. main() by import, not -m, so the module
# logs under its own name rather than __main__.
WINDOW_PROCESS: tuple[str, ...] = ("-P", "-c", "from markcom.window_process import main; main()")
MS_PER_SEC: int = 1000


class WebWindow(TrayTarget):
    """Web page in its own window. Build it after the QApplication; GUI thread only, as Qt
    requires. Each open loads the page afresh in a new window, which takes the last one's size
    and maximised state. As the app quits, an open window closes and its process ends."""

    def __init__(self, title: str, url: HttpUrl, icon: Path) -> None:
        self._title: str = title
        self._url: HttpUrl = url
        self._icon: Path = icon
        # None: no window open
        self._process: QProcess | None = None
        # Processes of closed windows, kept until they end: deleting a QProcess kills its process.
        self._ending: set[QProcess] = set()
        self._minimised: bool = False
        # None: no window yet, so the first takes config.json's size.
        self._geometry: bytes | None = None
        app: QCoreApplication | None = QApplication.instance()
        if app is None:
            no_app: str = "build the WebWindow after the QApplication"
            raise RuntimeError(no_app)
        # else Qt kills a still-running window process when it deletes its QProcess at exit
        app.aboutToQuit.connect(self._end_on_quit)

    @override
    def is_open(self) -> bool:
        return self._process is not None and not self._minimised

    @override
    def open(self) -> None:
        self._minimised = False
        if self._process is not None:
            logger.debug("Bringing the window back")
            self._process.write(SHOW + LINE_END)
            return
        # set before start(): a failure to start is signalled within it
        self._process = self._new_process()
        # scheme, host and port only: URL may carry a token
        logger.info(
            "Starting the window for %s://%s:%s", self._url.scheme, self._url.host, self._url.port
        )
        self._process.start()

    @override
    def close(self) -> None:
        if self._process is None:
            logger.debug("No window to close")
            return
        logger.debug("Closing the window")
        self._ending.add(self._process)
        # end of input: the window closes and its process ends
        self._process.closeWriteChannel()
        self._process = None

    def _new_process(self) -> QProcess:
        spec: WindowSpec = WindowSpec(
            title=self._title,
            url=self._url,
            icon=self._icon,
            log_level=logging.getLevelName(logging.getLogger().getEffectiveLevel()),
            geometry=self._geometry,
        )
        environment: QProcessEnvironment = QProcessEnvironment.systemEnvironment()
        environment.insert(SPEC_VARIABLE, spec.model_dump_json())
        process: QProcess = QProcess()
        process.setProgram(sys.executable)
        process.setArguments(list(WINDOW_PROCESS))
        process.setProcessEnvironment(environment)
        # the window's log goes where the app's does; its stdout carries reports
        process.setProcessChannelMode(QProcess.ProcessChannelMode.ForwardedErrorChannel)
        process.readyReadStandardOutput.connect(partial(self._read_reports, process))
        process.finished.connect(partial(self._on_finished, process))
        process.errorOccurred.connect(partial(self._on_error, process))
        return process

    def _read_reports(self, process: QProcess) -> None:
        while process.canReadLine():
            line: bytes = bytes(process.readLine().data())
            try:
                report: WindowReport = WindowReport.model_validate_json(line)
            except ValidationError:
                logger.warning(
                    "Ignored a %d-byte line from the window that is not a report", len(line)
                )
                continue
            logger.debug("Window report: minimised %s", report.minimised)
            self._geometry = report.geometry
            # a closed window's last report still carries its size, but not whether it is open
            if process is self._process:
                self._minimised = report.minimised

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
        # ended while open: its window was closed from its title bar, or it failed
        if process is self._process:
            self._process = None
        process.deleteLater()
        # as for a window in this process: without a tray, closing the last window quits the app
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
