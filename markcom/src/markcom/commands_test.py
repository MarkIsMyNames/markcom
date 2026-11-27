import os
import select
import sys
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import pytest

from markcom.commands import (
    CommandFailedError,
    CommandNotFoundError,
    CommandResult,
    CommandRunner,
    SubprocessRunner,
)

PYTHON: str = sys.executable
STOP_TIMEOUT: timedelta = timedelta(seconds=5)
# Child sends its pid only once it is ready (signal handler set), so the test never races it.
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
    return SubprocessRunner()


@pytest.fixture
def pid_fifo(tmp_path: Path) -> Path:
    path: Path = tmp_path / "pid"
    os.mkfifo(path)
    return path


def read_pid(fifo: Path) -> int:
    descriptor: int = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
    try:
        readable, _, _ = select.select([descriptor], [], [], READY_TIMEOUT_SECONDS)
        assert readable, "child never reported its pid"
        return int(os.read(descriptor, 64))
    finally:
        os.close(descriptor)


def is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def enter_background(runner: CommandRunner, args: list[str]) -> None:
    with runner.background(args, STOP_TIMEOUT):
        pass


def test_run_success_returns_none(runner):
    assert runner.run([PYTHON, "-c", "pass"]) is None


@pytest.mark.parametrize("returncode", [1, 3])
def test_run_nonzero_raises_failed_with_returncode(runner, returncode):
    with pytest.raises(CommandFailedError) as raised:
        runner.run([PYTHON, "-c", f"exit({returncode})"])
    assert raised.value.returncode == returncode
    assert raised.value.command == PYTHON


def test_run_with_input_nonzero_raises_failed(runner):
    with pytest.raises(CommandFailedError) as raised:
        runner.run_with_input([PYTHON, "-c", "exit(4)"], "y\n")
    assert raised.value.returncode == 4


def test_capture_nonzero_returns_result_no_raise(runner):
    script: str = "import sys; print('out'); print('err', file=sys.stderr); exit(2)"
    assert runner.capture([PYTHON, "-c", script]) == CommandResult(
        returncode=2, stdout="out\n", stderr="err\n"
    )


@pytest.mark.parametrize(
    "start",
    [
        lambda runner: runner.run(["markcom-no-such-command"]),
        lambda runner: runner.run_with_input(["markcom-no-such-command"], "y\n"),
        lambda runner: runner.capture(["markcom-no-such-command"]),
        lambda runner: enter_background(runner, ["markcom-no-such-command"]),
    ],
)
def test_missing_command_raises_not_found(runner, start: Callable[[CommandRunner], object]):
    with pytest.raises(CommandNotFoundError) as raised:
        start(runner)
    assert raised.value.command == "markcom-no-such-command"


def test_run_with_input_passes_stdin_text(runner):
    script: str = "import sys; exit(0 if sys.stdin.read() == 'y\\n' else 1)"
    assert runner.run_with_input([PYTHON, "-c", script], "y\n") is None


def test_background_stops_process_on_exit(runner, pid_fifo):
    with runner.background([PYTHON, "-c", SLEEPER, str(pid_fifo)], STOP_TIMEOUT):
        pid: int = read_pid(pid_fifo)
        assert is_running(pid)
    assert not is_running(pid)


def test_background_stops_process_when_body_raises(runner, pid_fifo):
    pids: list[int] = []

    def fail_inside_block() -> None:
        with runner.background([PYTHON, "-c", SLEEPER, str(pid_fifo)], STOP_TIMEOUT):
            pids.append(read_pid(pid_fifo))
            raise KeyError

    with pytest.raises(KeyError):
        fail_inside_block()
    assert not is_running(pids[0])


def test_background_kills_process_ignoring_terminate(runner, pid_fifo):
    with runner.background(
        [PYTHON, "-c", TERM_IGNORER, str(pid_fifo)], timedelta(milliseconds=100)
    ):
        pid: int = read_pid(pid_fifo)
    assert not is_running(pid)
