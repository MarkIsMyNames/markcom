"""Standard library only: importing pydantic would add a third to window start-up."""

from dataclasses import dataclass

# environment, not argv: any local user can read argv, and URL may carry a token
SPEC_VARIABLE: str = "MARKCOM_WINDOW_SPEC"


@dataclass(frozen=True)
class WindowSpec:
    title: str
    url: str
    icon: str
    width: int
    height: int
