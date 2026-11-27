"""Starts other programs from argument lists, never through a shell."""

import logging
import shutil
import subprocess
from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from datetime import timedelta
from typing import override

logger: logging.Logger = logging.getLogger(__name__)


class CommandError(Exception):
    """A command could not start or did not succeed."""


class CommandNotFoundError(CommandError):
    def __init__(self, command: str) -> None:
        super().__init__(f"{command} is not installed or not on PATH")
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


class CommandRunner(ABC):
    @abstractmethod
    def run(self, args: Sequence[str]) -> None:
        """Run with standard input and output left as they are.
        Raises CommandFailedError on a non-zero exit."""

    @abstractmethod
    def run_with_input(self, args: Sequence[str], stdin_text: str) -> None:
        """Run with stdin_text as standard input. Raises CommandFailedError on a non-zero exit."""

    @abstractmethod
    def capture(self, args: Sequence[str]) -> CommandResult:
        """Run quietly and return the exit code and output; a non-zero exit is not an error here,
        because callers use it to ask questions (is this installed?)."""

    @abstractmethod
    def background(
        self, args: Sequence[str], stop_timeout: timedelta
    ) -> AbstractContextManager[None]:
        """Run for the duration of the block; on exit terminate it, wait up to stop_timeout,
        then kill it if it has not ended."""


class SubprocessRunner(CommandRunner):
    @override
    def run(self, args: Sequence[str]) -> None:
        self._run_checked(args, None)

    @override
    def run_with_input(self, args: Sequence[str], stdin_text: str) -> None:
        self._run_checked(args, stdin_text)

    @override
    def capture(self, args: Sequence[str]) -> CommandResult:
        command: list[str] = self._resolve(args)
        logger.debug("Capturing %s", command)
        completed: subprocess.CompletedProcess[str] = subprocess.run(
            command, capture_output=True, text=True, check=False
        )
        logger.debug("%s exited with %d", args[0], completed.returncode)
        return CommandResult(
            returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr
        )

    @override
    @contextmanager
    def background(self, args: Sequence[str], stop_timeout: timedelta) -> Iterator[None]:
        command: list[str] = self._resolve(args)
        logger.info("Starting %s in the background", command)
        with subprocess.Popen(
            command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        ) as process:
            try:
                yield
            finally:
                process.terminate()
                try:
                    process.wait(timeout=stop_timeout.total_seconds())
                except subprocess.TimeoutExpired:
                    logger.warning(
                        "%s did not stop within %s of terminate; killing it", args[0], stop_timeout
                    )
                    process.kill()
        logger.info("Stopped %s, exit code %d", args[0], process.returncode)

    @staticmethod
    def _run_checked(args: Sequence[str], stdin_text: str | None) -> None:
        """stdin_text None leaves standard input as it is."""
        command: list[str] = SubprocessRunner._resolve(args)
        logger.info("Running %s", command)
        completed: subprocess.CompletedProcess[str] = subprocess.run(
            command, input=stdin_text, stderr=subprocess.PIPE, text=True, check=False
        )
        if completed.returncode != 0:
            logger.error(
                "%s failed with exit code %d: %s", args[0], completed.returncode, completed.stderr
            )
            raise CommandFailedError(args[0], completed.returncode)
        logger.info("Finished %s", args[0])

    @staticmethod
    def _resolve(args: Sequence[str]) -> list[str]:
        executable: str | None = shutil.which(args[0])
        if executable is None:
            raise CommandNotFoundError(args[0])
        return [executable, *args[1:]]
