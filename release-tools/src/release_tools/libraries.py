import json
import tomllib
from abc import ABC, abstractmethod
from pathlib import Path, PurePosixPath
from typing import Any, ClassVar, override

from git import GitCommandError, Repo
from markcom.config import load_config
from semver import Version
from tomlkit.items import AoT, Table
from tomlkit.toml_document import TOMLDocument
from tomlkit.toml_file import TOMLFile

from release_tools.config import LibraryConfig, LibraryKind, ReleaseConfig

ENCODING: str = "utf-8"
HEAD: str = "HEAD"
REMOTE: str = "origin"
MAIN: str = "main"
REMOTE_MAIN: str = f"{REMOTE}/{MAIN}"

CODE_FOLDER: str = "src"
PYPROJECT: str = "pyproject.toml"
UV_LOCK: str = "uv.lock"
PACKAGE_JSON: str = "package.json"
PACKAGE_LOCK: str = "package-lock.json"
VERSION_KEY: str = "version"
NAME_KEY: str = "name"
PROJECT_TABLE: str = "project"
UV_LOCK_PACKAGES: str = "package"
NPM_LOCK_PACKAGES: str = "packages"
NPM_ROOT_PACKAGE: str = ""
# npm's own formatting
NPM_INDENT: int = 2


class VersionError(ValueError): ...


class Library(ABC):
    manifest: ClassVar[str]
    # test globs: a test-only change releases nothing
    tests: ClassVar[tuple[str, ...]]

    def __init__(self, config: LibraryConfig) -> None:
        self.config: LibraryConfig = config
        self._folder: PurePosixPath = PurePosixPath(config.path)
        # in a git glob, **/ matches any depth, even none
        self._code: tuple[str, ...] = (
            *(
                str(self._folder / path)
                for path in (CODE_FOLDER, self.manifest, *config.extra_code)
            ),
            *(f":(exclude,glob){self._folder / pattern}" for pattern in self.tests),
        )

    def tag(self, version: Version) -> str:
        return f"{self.config.tag_prefix}{version}"

    def exists_at(self, repo: Repo, revision: str) -> bool:
        try:
            repo.commit(revision).tree / str(self._folder / self.manifest)
        except KeyError:
            return False
        return True

    def version_at(self, repo: Repo, revision: str) -> Version:
        try:
            manifest: str = repo.git.show(f"{revision}:{self._folder / self.manifest}")
            text: str = self._version(manifest)
        except (GitCommandError, ValueError, KeyError, TypeError) as failure:
            unreadable: str = f"could not read {self.config.name}'s version at {revision}"
            raise VersionError(unreadable) from failure
        try:
            return Version.parse(text)
        except ValueError as failure:
            malformed: str = f"{self.config.name}: version {text} is not of the form X.Y.Z"
            raise VersionError(malformed) from failure

    def latest_release(self, repo: Repo) -> Version | None:
        return max(
            (
                Version.parse(tag.name.removeprefix(self.config.tag_prefix))
                for tag in repo.tags
                if tag.name.startswith(self.config.tag_prefix)
            ),
            default=None,
        )

    def changed(self, repo: Repo, since: str, until: str) -> bool:
        return bool(repo.git.diff("--name-only", since, until, "--", *self._code))

    @staticmethod
    @abstractmethod
    def _version(manifest: str) -> str: ...

    @abstractmethod
    def write_version(self, root: Path, version: Version) -> None: ...


class PythonLibrary(Library):
    manifest: ClassVar[str] = PYPROJECT
    tests: ClassVar[tuple[str, ...]] = ("**/*_test.py", "**/conftest.py")

    @override
    @staticmethod
    def _version(manifest: str) -> str:
        return str(tomllib.loads(manifest)[PROJECT_TABLE][VERSION_KEY])

    @override
    def write_version(self, root: Path, version: Version) -> None:
        pyproject_file: TOMLFile = TOMLFile(root / self._folder / self.manifest)
        pyproject: TOMLDocument = pyproject_file.read()
        project: Table = pyproject[PROJECT_TABLE]
        project[VERSION_KEY] = str(version)
        pyproject_file.write(pyproject)
        lock_file: TOMLFile = TOMLFile(root / self._folder / UV_LOCK)
        lock: TOMLDocument = lock_file.read()
        packages: AoT = lock[UV_LOCK_PACKAGES]
        own: Table = next(package for package in packages if package[NAME_KEY] == project[NAME_KEY])
        own[VERSION_KEY] = str(version)
        lock_file.write(lock)


class NpmLibrary(Library):
    manifest: ClassVar[str] = PACKAGE_JSON
    tests: ClassVar[tuple[str, ...]] = ("**/*.test.ts",)

    @override
    @staticmethod
    def _version(manifest: str) -> str:
        return str(json.loads(manifest)[VERSION_KEY])

    @override
    def write_version(self, root: Path, version: Version) -> None:
        manifest_path: Path = root / self._folder / self.manifest
        manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding=ENCODING))
        manifest[VERSION_KEY] = str(version)
        lock_path: Path = root / self._folder / PACKAGE_LOCK
        lock: dict[str, Any] = json.loads(lock_path.read_text(encoding=ENCODING))
        # package-lock.json repeats the version in its root package entry
        lock[VERSION_KEY] = str(version)
        lock[NPM_LOCK_PACKAGES][NPM_ROOT_PACKAGE][VERSION_KEY] = str(version)
        for path, data in ((manifest_path, manifest), (lock_path, lock)):
            text: str = json.dumps(data, indent=NPM_INDENT, ensure_ascii=False)
            path.write_text(f"{text}\n", encoding=ENCODING)


KINDS: dict[LibraryKind, type[Library]] = {
    LibraryKind.UV: PythonLibrary,
    LibraryKind.NPM: NpmLibrary,
}


def load_libraries(root: Path, file_name: str) -> tuple[Library, ...]:
    config: ReleaseConfig = load_config(root / file_name, ReleaseConfig)
    return tuple(KINDS[library.kind](library) for library in config.libraries)
