import os
import sys
from pathlib import Path

from release_tools.libraries import ENCODING

OUTPUT_VARIABLE: str = "GITHUB_OUTPUT"


def say(message: str) -> None:
    sys.stdout.write(f"{message}\n")


def error(message: str) -> None:
    # GitHub Actions shows a line starting ::error:: as an error on the run
    say(f"::error::{message}")


def set_output(name: str, value: str) -> None:
    with Path(os.environ[OUTPUT_VARIABLE]).open("a", encoding=ENCODING) as output:
        output.write(f"{name}={value}\n")
