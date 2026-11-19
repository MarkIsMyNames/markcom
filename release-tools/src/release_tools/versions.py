import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Self, override

VERSION_PATTERN = re.compile(r"(\d+)\.(\d+)\.(\d+)")
MINOR_LABEL = "release:minor"
MAJOR_LABEL = "release:major"


class InvalidVersionError(ValueError):
    def __init__(self, text: str) -> None:
        super().__init__(f"{text!r} is not a version of the form X.Y.Z")
        self.text = text


class BumpLevel(StrEnum):
    PATCH = "patch"
    MINOR = "minor"
    MAJOR = "major"


def bump_level(labels: Iterable[str]) -> BumpLevel:
    """The bump a merged pull request's labels ask for; the larger wins."""
    names = set(labels)
    if MAJOR_LABEL in names:
        return BumpLevel.MAJOR
    if MINOR_LABEL in names:
        return BumpLevel.MINOR
    return BumpLevel.PATCH


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

    def bump(self, level: BumpLevel) -> Self:
        match level:
            case BumpLevel.PATCH:
                return type(self)(self.major, self.minor, self.patch + 1)
            case BumpLevel.MINOR:
                return type(self)(self.major, self.minor + 1, 0)
            case BumpLevel.MAJOR:
                return type(self)(self.major + 1, 0, 0)

    @override
    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"
