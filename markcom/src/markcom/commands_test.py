import os
import select
import sys
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import pytest

from markcom.commands import CommandRunner, SubprocessRunner

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


def enter_background(runner: CommandRunner, args: list[str]) -> None:
    with runner.run_in_background(args, STOP_TIMEOUT):
        pass


@pytest.mark.parametrize("returncode", [0, 2])
def test_run_returns_the_exit_code_and_output_without_raising(
    runner: CommandRunner, returncode: int
) -> None:
    script: str = f"import sys; print('out'); print('err', file=sys.stderr); exit({returncode})"
    completed = runner.run([PYTHON, "-c", script])
    assert (completed.returncode, completed.stdout, completed.stderr) == (
        returncode,
        "out\n",
        "err\n",
    )


@pytest.mark.parametrize("start", [run_args, enter_background])
def test_missing_command_raises_not_found(
    runner: CommandRunner, start: Callable[[CommandRunner, list[str]], None]
) -> None:
    with pytest.raises(FileNotFoundError):
        start(runner, [MISSING])


@pytest.mark.parametrize("start", [run_args, enter_background])
def test_a_program_not_allowed_is_refused(
    runner: CommandRunner, start: Callable[[CommandRunner, list[str]], None]
) -> None:
    with pytest.raises(PermissionError):
        start(runner, ["true"])


def test_the_child_gets_only_the_given_environment(runner: CommandRunner) -> None:
    script: str = "import os; print(sorted(k for k in os.environ if k != 'LC_CTYPE'))"
    assert runner.run([PYTHON, "-c", script]).stdout == "['MARKCOM_TEST', 'PATH']\n"


def test_run_passes_stdin_text(runner: CommandRunner) -> None:
    script: str = "import sys; exit(0 if sys.stdin.read() == 'y\\n' else 1)"
    assert runner.run([PYTHON, "-c", script], "y\n").returncode == 0


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
