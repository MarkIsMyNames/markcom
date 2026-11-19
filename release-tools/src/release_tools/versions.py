import re
from dataclasses import dataclass
from typing import Self, override

VERSION_PATTERN = re.compile(r"(\d+)\.(\d+)\.(\d+)")


class InvalidVersionError(ValueError):
    def __init__(self, text: str) -> None:
        super().__init__(f"{text!r} is not a version of the form X.Y.Z")
        self.text = text


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, text: str) -> Self:
        match = VERSION_PATTERN.fullmatch(text)
        if match is None:
            raise InvalidVersionError(text)
        major, minor, patch = (int(part) for part in match.groups())
        return cls(major, minor, patch)

    @override
    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"
