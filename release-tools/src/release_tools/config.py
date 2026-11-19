"""release.json, at the root of the repository being released: the libraries in it."""

from enum import StrEnum
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, ValidationError

from release_tools.constants import ENCODING

RELEASE_CONFIG = "release.json"


class ConfigError(ValueError):
    """release.json is missing or invalid; the message names the file."""


class StrictModel(BaseModel):
    """Every field required, unknown keys rejected, immutable."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True, strict=True)


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
    path = root / RELEASE_CONFIG
    try:
        return ReleaseConfig.model_validate_json(path.read_text(encoding=ENCODING))
    except FileNotFoundError as error:
        message = f"{RELEASE_CONFIG}: file not found at the repository root"
        raise ConfigError(message) from error
    except ValidationError as error:
        message = f"{RELEASE_CONFIG}: {error}"
        raise ConfigError(message) from error
