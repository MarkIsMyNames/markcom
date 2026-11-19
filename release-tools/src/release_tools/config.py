"""release.json, at the root of the repository being released: the libraries in it."""

from enum import StrEnum
from pathlib import Path

from markcom.config import StrictModel, load_config

RELEASE_CONFIG = "release.json"


class LibraryKind(StrEnum):
    UV = "uv"
    NPM = "npm"


class LibraryConfig(StrictModel):
    # shown in messages and release commits
    name: str
    kind: LibraryKind
    # the library's folder, relative to the repository root; "." for the root
    path: str
    # a release is tagged <tag_prefix><version>
    tag_prefix: str
    # files of its code outside src, relative to its folder
    extra_code: tuple[str, ...]


class ReleaseConfig(StrictModel):
    libraries: tuple[LibraryConfig, ...]


def load_release_config(root: Path) -> ReleaseConfig:
    """Raises markcom's ConfigError, naming the file, when it is missing or invalid."""
    return load_config(root / RELEASE_CONFIG, ReleaseConfig)
