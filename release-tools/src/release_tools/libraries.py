import json
import tomllib
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar, cast, override

import tomlkit
from git import GitCommandError, Repo
from tomlkit.items import AoT, Table

from release_tools.constants import ENCODING, TAG_SEPARATOR, VERSION_KEY
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
    """One library this repository releases, in the folder named after it. A release follows a
    change to its code: its `src` folder, any `extra_code` files and its manifest, tests
    excluded."""

    manifest: ClassVar[str]
    tests: ClassVar[str]

    def __init__(self, name: str, extra_code: tuple[str, ...] = ()) -> None:
        self.name = name
        # git pathspecs from the repository root; an exclude pattern's * also matches /
        self._code = (
            *(f"{name}/{path}" for path in (CODE_FOLDER, self.manifest, *extra_code)),
            f":(exclude){name}/{self.tests}",
        )

    def tag(self, version: Version) -> str:
        return f"{self.name}{TAG_SEPARATOR}{version}"

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
        prefix = f"{self.name}{TAG_SEPARATOR}"
        tags = [tag.name for tag in repo.tags if tag.name.startswith(prefix)]
        return max((Version.parse(tag.removeprefix(prefix)) for tag in tags), default=None)

    def changed(self, repo: Repo, since: str, until: str) -> bool:
        return bool(repo.git.diff("--name-only", since, until, "--", *self._code))

    def _manifest_at(self, repo: Repo, revision: str) -> str:
        return str(repo.git.show(f"{revision}:{self.name}/{self.manifest}"))

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
        pyproject_path = root / self.name / self.manifest
        pyproject = tomlkit.parse(pyproject_path.read_text(encoding=ENCODING))
        cast("Table", pyproject[PROJECT_TABLE])[VERSION_KEY] = str(version)
        pyproject_path.write_text(tomlkit.dumps(pyproject), encoding=ENCODING)
        lock_path = root / self.name / UV_LOCK
        lock = tomlkit.parse(lock_path.read_text(encoding=ENCODING))
        for package in cast("AoT", lock["package"]):
            if package["name"] == self.name:
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
        for path in (root / self.name / self.manifest, root / self.name / PACKAGE_LOCK):
            data = json.loads(path.read_text(encoding=ENCODING))
            data[VERSION_KEY] = str(version)
            # package-lock.json repeats the version in its root package entry
            if "packages" in data:
                data["packages"][""][VERSION_KEY] = str(version)
            text = json.dumps(data, indent=NPM_INDENT, ensure_ascii=False)
            path.write_text(f"{text}\n", encoding=ENCODING)


LIBRARIES: tuple[Library, ...] = (
    PythonLibrary("markcom"),
    # projects extend these two files directly, so they are web-config's code
    NpmLibrary("markcom-web-config", extra_code=("tsconfig.json", "prettier.json")),
    NpmLibrary("markcom-i18n"),
)
