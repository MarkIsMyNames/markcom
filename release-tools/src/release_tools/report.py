import sys


def say(message: str) -> None:
    sys.stdout.write(f"{message}\n")


def error(message: str) -> None:
    # GitHub Actions shows a line starting ::error:: as an error on the run
    say(f"::error::{message}")
