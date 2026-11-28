from enum import StrEnum
from pathlib import Path

from markcom.config import BaseAppConfig, StrictModel

CONFIG_PATH: Path = Path(__file__).with_name("config.json")


class Labels(StrictModel):
    minor: str
    major: str


class Bot(StrictModel):
    name: str
    email: str


class ToolConfig(BaseAppConfig):
    release_config: str
    labels: Labels
    release_commit_prefix: str
    bot: Bot


class LibraryKind(StrEnum):
    UV = "uv"
    NPM = "npm"


class LibraryConfig(StrictModel):
    name: str
    kind: LibraryKind
    path: str
    tag_prefix: str
    extra_code: tuple[str, ...]


class ReleaseConfig(StrictModel):
    libraries: tuple[LibraryConfig, ...]
