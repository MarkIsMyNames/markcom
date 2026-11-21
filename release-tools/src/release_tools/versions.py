from collections.abc import Iterable
from enum import StrEnum

from release_tools.config import Labels


class BumpLevel(StrEnum):
    """Named as semver's Version.next_version parts."""

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
