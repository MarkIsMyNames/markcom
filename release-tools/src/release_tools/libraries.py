import json
import tomllib
from abc import ABC, abstractmethod
from pathlib import Path, PurePosixPath
from typing import ClassVar, cast, override

import tomlkit
from git import GitCommandError, Repo
from tomlkit.items import AoT, Table

from release_tools.config import LibraryConfig, LibraryKind, load_release_config
from release_tools.constants import ENCODING, VERSION_KEY
from release_tools.versions import InvalidVersionError, Version

CODE_FOLDER = "src"
PYPROJECT = "pyproject.toml"
UV_LOCK = "uv.lock"
PACKAGE_JSON = "package.json"
PACKAGE_LOCK = "package-lock.json"
PROJECT_TABLE = "project"
# npm's own formatting
NPM_INDENT = 2


class VersionError(ValueError):
    """A library's version is unreadable or not X.Y.Z; the message names the library."""


class Library(ABC):
    """One library release.json lists. A release follows a change to its code: its `src` folder,
    its manifest and any `extra_code` files, tests excluded."""

    manifest: ClassVar[str]
    tests: ClassVar[str]

    def __init__(self, config: LibraryConfig) -> None:
        self.name = config.name
        self._folder = PurePosixPath(config.path)
        self._tag_prefix = config.tag_prefix
        # git pathspecs from the repository root; an exclude pattern's * also matches /
        code = (CODE_FOLDER, self.manifest, *config.extra_code)
        self._code = (
            *(str(self._folder / path) for path in code),
            f":(exclude){self._folder / self.tests}",
        )

    def tag(self, version: Version) -> str:
        return f"{self._tag_prefix}{version}"

    def exists_at(self, repo: Repo, revision: str) -> bool:
        """Whether its manifest is in the repository at a git revision."""
        try:
            repo.commit(revision).tree / str(self._folder / self.manifest)
        except KeyError:
            return False
        return True

    def version_at(self, repo: Repo, revision: str) -> Version:
        try:
            text = self._version(self._manifest_at(repo, revision))
        except (GitCommandError, ValueError, KeyError, TypeError) as error:
            message = f"could not read {self.name}'s version at {revision}"
            raise VersionError(message) from error
        try:
            return Version.parse(text)
        except InvalidVersionError as error:
            message = f"{self.name}: version {text} is not of the form X.Y.Z"
            raise VersionError(message) from error

    def latest_release(self, repo: Repo) -> Version | None:
        """The highest version tagged, or None before its first release."""
        prefix = self._tag_prefix
        tags = [tag.name for tag in repo.tags if tag.name.startswith(prefix)]
        return max((Version.parse(tag.removeprefix(prefix)) for tag in tags), default=None)

    def changed(self, repo: Repo, since: str, until: str) -> bool:
        return bool(repo.git.diff("--name-only", since, until, "--", *self._code))

    def _manifest_at(self, repo: Repo, revision: str) -> str:
        return str(repo.git.show(f"{revision}:{self._folder / self.manifest}"))

    @abstractmethod
    def _version(self, manifest: str) -> str: ...

    @abstractmethod
    def write_version(self, root: Path, version: Version) -> None:
        """Writes the version into its manifest and lock file in the working tree at `root`."""


class PythonLibrary(Library):
    manifest = PYPROJECT
    tests = "*_test.py"

    @override
    def _version(self, manifest: str) -> str:
        return str(tomllib.loads(manifest)[PROJECT_TABLE][VERSION_KEY])

    @override
    def write_version(self, root: Path, version: Version) -> None:
        pyproject_path = root / self._folder / self.manifest
        pyproject = tomlkit.parse(pyproject_path.read_text(encoding=ENCODING))
        project = cast("Table", pyproject[PROJECT_TABLE])
        project[VERSION_KEY] = str(version)
        pyproject_path.write_text(tomlkit.dumps(pyproject), encoding=ENCODING)
        lock_path = root / self._folder / UV_LOCK
        lock = tomlkit.parse(lock_path.read_text(encoding=ENCODING))
        for package in cast("AoT", lock["package"]):
            if package["name"] == project["name"]:
                package[VERSION_KEY] = str(version)
        lock_path.write_text(tomlkit.dumps(lock), encoding=ENCODING)


class NpmLibrary(Library):
    manifest = PACKAGE_JSON
    tests = "*.test.ts"

    @override
    def _version(self, manifest: str) -> str:
        return str(json.loads(manifest)[VERSION_KEY])

    @override
    def write_version(self, root: Path, version: Version) -> None:
        for path in (root / self._folder / self.manifest, root / self._folder / PACKAGE_LOCK):
            data = json.loads(path.read_text(encoding=ENCODING))
            data[VERSION_KEY] = str(version)
            # package-lock.json repeats the version in its root package entry
            if "packages" in data:
                data["packages"][""][VERSION_KEY] = str(version)
            text = json.dumps(data, indent=NPM_INDENT, ensure_ascii=False)
            path.write_text(f"{text}\n", encoding=ENCODING)


KINDS: dict[LibraryKind, type[Library]] = {
    LibraryKind.UV: PythonLibrary,
    LibraryKind.NPM: NpmLibrary,
}


def load_libraries(root: Path) -> tuple[Library, ...]:
    """The libraries the release.json at `root` lists."""
    return tuple(KINDS[library.kind](library) for library in load_release_config(root).libraries)
