import os
import select
import sys
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import pytest

from markcom.commands import (
    CommandFailedError,
    CommandNotAllowedError,
    CommandNotFoundError,
    CommandResult,
    CommandRunner,
    SubprocessRunner,
)

PYTHON: str = sys.executable
MISSING: str = "markcom-no-such-command"
ENVIRONMENT: dict[str, str] = {"PATH": os.environ["PATH"], "MARKCOM_TEST": "given"}
STOP_TIMEOUT: timedelta = timedelta(seconds=5)
# child sends pid only once ready (handler set): test never races it
READY_TIMEOUT_SECONDS: float = 30.0
SLEEPER: str = (
    "import os, sys, time; open(sys.argv[1], 'w').write(str(os.getpid())); time.sleep(600)"
)
TERM_IGNORER: str = (
    "import os, signal, sys, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
    "open(sys.argv[1], 'w').write(str(os.getpid())); time.sleep(600)"
)


@pytest.fixture
def runner() -> CommandRunner:
    return SubprocessRunner(frozenset({PYTHON, MISSING}), ENVIRONMENT)


@pytest.fixture
def pid_fifo(tmp_path: Path) -> Path:
    path: Path = tmp_path / "pid"
    os.mkfifo(path)
    return path


def read_pid(fifo: Path) -> int:
    with os.fdopen(os.open(fifo, os.O_RDONLY | os.O_NONBLOCK), "rb", buffering=0) as reader:
        readable, _, _ = select.select([reader], [], [], READY_TIMEOUT_SECONDS)
        assert readable, "child never reported its pid"
        return int(reader.read())


def is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def run_args(runner: CommandRunner, args: list[str]) -> None:
    runner.run(args)


def run_args_with_input(runner: CommandRunner, args: list[str]) -> None:
    runner.run_with_input(args, "y\n")


def capture_args(runner: CommandRunner, args: list[str]) -> None:
    runner.capture(args)


def enter_background(runner: CommandRunner, args: list[str]) -> None:
    with runner.run_in_background(args, STOP_TIMEOUT):
        pass


def test_run_success_returns_none(runner: CommandRunner) -> None:
    assert runner.run([PYTHON, "-c", "pass"]) is None


@pytest.mark.parametrize("start", [run_args, run_args_with_input])
@pytest.mark.parametrize("returncode", [1, 3])
def test_run_nonzero_raises_failed_with_returncode(
    runner: CommandRunner, start: Callable[[CommandRunner, list[str]], None], returncode: int
) -> None:
    with pytest.raises(CommandFailedError):
        start(runner, [PYTHON, "-c", f"exit({returncode})"])


def test_capture_nonzero_returns_result_no_raise(runner: CommandRunner) -> None:
    script: str = "import sys; print('out'); print('err', file=sys.stderr); exit(2)"
    assert runner.capture([PYTHON, "-c", script]) == CommandResult(returncode=2, stdout="out\n")


@pytest.mark.parametrize("start", [run_args, run_args_with_input, capture_args, enter_background])
def test_missing_command_raises_not_found(
    runner: CommandRunner, start: Callable[[CommandRunner, list[str]], None]
) -> None:
    with pytest.raises(CommandNotFoundError):
        start(runner, [MISSING])


@pytest.mark.parametrize("start", [run_args, run_args_with_input, capture_args, enter_background])
def test_a_program_not_allowed_is_refused(
    runner: CommandRunner, start: Callable[[CommandRunner, list[str]], None]
) -> None:
    with pytest.raises(CommandNotAllowedError):
        start(runner, ["true"])


def test_the_child_gets_only_the_given_environment(runner: CommandRunner) -> None:
    script: str = "import os; print(sorted(k for k in os.environ if k != 'LC_CTYPE'))"
    assert runner.capture([PYTHON, "-c", script]).stdout == "['MARKCOM_TEST', 'PATH']\n"


def test_run_with_input_passes_stdin_text(runner: CommandRunner) -> None:
    script: str = "import sys; exit(0 if sys.stdin.read() == 'y\\n' else 1)"
    assert runner.run_with_input([PYTHON, "-c", script], "y\n") is None


def test_background_stops_process_on_exit(runner: CommandRunner, pid_fifo: Path) -> None:
    with runner.run_in_background([PYTHON, "-c", SLEEPER, str(pid_fifo)], STOP_TIMEOUT):
        pid: int = read_pid(pid_fifo)
        assert is_running(pid)
    assert not is_running(pid)


def test_background_stops_process_when_body_raises(runner: CommandRunner, pid_fifo: Path) -> None:
    pids: list[int] = []

    def fail_inside_block() -> None:
        with runner.run_in_background([PYTHON, "-c", SLEEPER, str(pid_fifo)], STOP_TIMEOUT):
            pids.append(read_pid(pid_fifo))
            raise KeyError

    with pytest.raises(KeyError):
        fail_inside_block()
    assert not is_running(pids[0])


def test_background_kills_process_ignoring_terminate(runner: CommandRunner, pid_fifo: Path) -> None:
    with runner.run_in_background(
        [PYTHON, "-c", TERM_IGNORER, str(pid_fifo)], timedelta(milliseconds=100)
    ):
        pid: int = read_pid(pid_fifo)
    assert not is_running(pid)
