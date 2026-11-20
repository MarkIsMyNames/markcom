"""release-tools' own settings (config.json beside this file), and the library list of the
repository being released (release.json at its root)."""

from enum import StrEnum
from pathlib import Path

from markcom.config import BaseAppConfig, StrictModel, load_config

CONFIG_PATH = Path(__file__).with_name("config.json")


class Labels(StrictModel):
    """Pull request labels that ask for more than a patch."""

    minor: str
    major: str


class Bot(StrictModel):
    """Who release commits and tags are made as."""

    name: str
    email: str


class ToolConfig(BaseAppConfig):
    # the file, at the repository root, that lists its libraries
    release_config: str
    labels: Labels
    release_commit_prefix: str
    # the visual-baselines workflow's commit
    baselines_commit_message: str
    bot: Bot


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


def load_release_config(root: Path, file_name: str) -> ReleaseConfig:
    """Raises markcom's ConfigError, naming the file, when it is missing or invalid."""
    return load_config(root / file_name, ReleaseConfig)
