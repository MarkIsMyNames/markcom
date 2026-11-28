import logging
import subprocess
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from datetime import timedelta
from types import TracebackType
from typing import override

logger: logging.Logger = logging.getLogger(__name__)


class BackgroundProcess(AbstractContextManager[None]):
    def __init__(
        self, args: Sequence[str], environment: Mapping[str, str], stop_timeout: timedelta
    ) -> None:
        self._name: str = args[0]
        logger.info("Starting %s in the background", self._name)
        self._stop_timeout: timedelta = stop_timeout
        self._process: subprocess.Popen[bytes] = subprocess.Popen(
            args, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

    @override
    def __exit__(
        self,
        _type: type[BaseException] | None,
        _error: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        with self._process as process:
            process.terminate()
            try:
                process.wait(timeout=self._stop_timeout.total_seconds())
            except subprocess.TimeoutExpired:
                logger.warning(
                    "%s did not stop within %s of terminate, so it is killed",
                    self._name,
                    self._stop_timeout,
                )
                process.kill()
                process.wait()
        logger.info("Stopped %s, exit code %d", self._name, process.returncode)


class CommandRunner(ABC):
    @abstractmethod
    def run(self, args: Sequence[str]) -> None: ...

    # prompts such as sdkmanager --licenses wait for "y" on stdin
    @abstractmethod
    def run_with_input(self, args: Sequence[str], stdin_text: str) -> None: ...

    # never raises on non-zero: exit code is the answer (is this installed?)
    @abstractmethod
    def capture(self, args: Sequence[str]) -> subprocess.CompletedProcess[str]: ...

    # terminated on leaving the with block, killed after stop_timeout
    @abstractmethod
    def run_in_background(
        self, args: Sequence[str], stop_timeout: timedelta
    ) -> AbstractContextManager[None]: ...


class SubprocessRunner(CommandRunner):
    # subprocess finds programs on environment's PATH, not the parent's
    def __init__(self, programs: frozenset[str], environment: Mapping[str, str]) -> None:
        self._programs: frozenset[str] = programs
        self._environment: dict[str, str] = dict(environment)

    @override
    def run(self, args: Sequence[str]) -> None:
        self._run_checked(args, None)

    @override
    def run_with_input(self, args: Sequence[str], stdin_text: str) -> None:
        self._run_checked(args, stdin_text)

    @override
    def capture(self, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
        self._check_allowed(args)
        logger.debug("Capturing %s", args[0])
        completed: subprocess.CompletedProcess[str] = subprocess.run(
            args, env=self._environment, capture_output=True, text=True, check=False
        )
        logger.debug("%s exited with %d", args[0], completed.returncode)
        return completed

    @override
    def run_in_background(
        self, args: Sequence[str], stop_timeout: timedelta
    ) -> AbstractContextManager[None]:
        self._check_allowed(args)
        return BackgroundProcess(args, self._environment, stop_timeout)

    def _run_checked(self, args: Sequence[str], stdin_text: str | None) -> None:
        self._check_allowed(args)
        logger.info("Running %s", args[0])
        # input None leaves stdin as the caller's
        subprocess.run(args, input=stdin_text, env=self._environment, text=True, check=True)
        logger.info("Finished %s", args[0])

    def _check_allowed(self, args: Sequence[str]) -> None:
        if args[0] not in self._programs:
            not_allowed: str = f"{args[0]} is not one of the programs this runner may start"
            raise PermissionError(not_allowed)
