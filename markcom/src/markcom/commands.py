import logging
import os
import shutil
import subprocess
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from types import TracebackType
from typing import Self, override

logger: logging.Logger = logging.getLogger(__name__)

PATH_VARIABLE: str = "PATH"


class CommandError(Exception): ...


class CommandNotFoundError(CommandError):
    def __init__(self, command: str) -> None:
        super().__init__(f"{command} is not installed or not on PATH")
        self._command: str = command

    @property
    def command(self) -> str:
        return self._command


class CommandNotAllowedError(CommandError):
    def __init__(self, command: str) -> None:
        super().__init__(f"{command} is not one of the programs this runner may start")
        self._command: str = command

    @property
    def command(self) -> str:
        return self._command


class CommandFailedError(CommandError):
    def __init__(self, command: str, returncode: int) -> None:
        super().__init__(f"{command} failed with exit code {returncode}")
        self._command: str = command
        self._returncode: int = returncode

    @property
    def command(self) -> str:
        return self._command

    @property
    def returncode(self) -> int:
        return self._returncode


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class BackgroundProcess:
    """Runs for a `with` block; on exit, terminated, then killed after `stop_timeout`."""

    def __init__(
        self, command: list[str], environment: Mapping[str, str], stop_timeout: timedelta
    ) -> None:
        self._command: list[str] = command
        self._environment: dict[str, str] = dict(environment)
        self._name: str = command[0]
        self._stop_timeout: timedelta = stop_timeout
        self._process: subprocess.Popen[bytes] | None = None

    def __enter__(self) -> Self:
        logger.info("Starting %s in the background", self._name)
        self._process = subprocess.Popen(
            self._command,
            env=self._environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return self

    def __exit__(
        self,
        _type: type[BaseException] | None,
        _error: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        if self._process is None:
            return
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

    @abstractmethod
    def run_with_input(self, args: Sequence[str], stdin_text: str) -> None:
        """For prompts such as sdkmanager --licenses, which waits for "y" on stdin."""

    @abstractmethod
    def capture(self, args: Sequence[str]) -> CommandResult:
        """Never raises on non-zero: callers use the exit code to ask (is this installed?)."""

    @abstractmethod
    def background(self, args: Sequence[str], stop_timeout: timedelta) -> BackgroundProcess: ...


class SubprocessRunner(CommandRunner):
    """Starts only `programs`, each found on `environment`'s PATH and given only `environment`."""

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
    def capture(self, args: Sequence[str]) -> CommandResult:
        command: list[str] = self._resolve(args)
        logger.debug("Capturing %s", args[0])
        completed: subprocess.CompletedProcess[str] = subprocess.run(
            command, env=self._environment, capture_output=True, text=True, check=False
        )
        logger.debug("%s exited with %d", args[0], completed.returncode)
        return CommandResult(
            returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr
        )

    @override
    def background(self, args: Sequence[str], stop_timeout: timedelta) -> BackgroundProcess:
        return BackgroundProcess(self._resolve(args), self._environment, stop_timeout)

    def _run_checked(self, args: Sequence[str], stdin_text: str | None) -> None:
        command: list[str] = self._resolve(args)
        logger.info("Running %s", args[0])
        # input None leaves stdin as the caller's
        completed: subprocess.CompletedProcess[str] = subprocess.run(
            command, input=stdin_text, env=self._environment, text=True, check=False
        )
        if completed.returncode != os.EX_OK:
            raise CommandFailedError(args[0], completed.returncode)
        logger.info("Finished %s", args[0])

    def _resolve(self, args: Sequence[str]) -> list[str]:
        if args[0] not in self._programs:
            raise CommandNotAllowedError(args[0])
        # the given PATH, not the parent's: whoever sets PATH picks the binary
        executable: str | None = shutil.which(args[0], path=self._environment[PATH_VARIABLE])
        if executable is None:
            raise CommandNotFoundError(args[0])
        return [executable, *args[1:]]
