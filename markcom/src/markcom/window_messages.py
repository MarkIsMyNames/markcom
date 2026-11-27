"""Standard library only: importing pydantic would add a third to window start-up."""

import json
from dataclasses import asdict, dataclass
from typing import Self

# environment, not argv: any local user can read argv, and URL may carry a token
SPEC_VARIABLE: str = "MARKCOM_WINDOW_SPEC"


@dataclass(frozen=True)
class WindowSpec:
    title: str
    url: str
    icon: str
    width: int
    height: int

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, text: str) -> Self:
        # parent process wrote it, so trusted
        return cls(**json.loads(text))
