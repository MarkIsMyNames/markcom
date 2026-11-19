import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Self, override

from release_tools.config import Labels

VERSION_PATTERN = re.compile(r"(\d+)\.(\d+)\.(\d+)")


class InvalidVersionError(ValueError):
    def __init__(self, text: str) -> None:
        super().__init__(f"{text!r} is not a version of the form X.Y.Z")
        self.text = text


class BumpLevel(StrEnum):
    PATCH = "patch"
    MINOR = "minor"
    MAJOR = "major"


def bump_level(names: Iterable[str], labels: Labels) -> BumpLevel:
    """The bump a merged pull request's label names ask for; the larger wins."""
    given = set(names)
    if labels.major in given:
        return BumpLevel.MAJOR
    if labels.minor in given:
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
        if level is BumpLevel.MAJOR:
            return type(self)(self.major + 1, 0, 0)
        if level is BumpLevel.MINOR:
            return type(self)(self.major, self.minor + 1, 0)
        return type(self)(self.major, self.minor, self.patch + 1)

    @override
    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"
