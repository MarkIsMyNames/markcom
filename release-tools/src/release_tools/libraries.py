import json
import tomllib
from abc import ABC, abstractmethod
from typing import override

from git import GitCommandError, Repo

from release_tools.versions import Version


class UnreadableVersionError(RuntimeError):
    def __init__(self, library: str, revision: str) -> None:
        super().__init__(f"could not read {library}'s version at {revision}")


class Library(ABC):
    """One library this repository releases, in the folder named after it."""

    def __init__(self, name: str) -> None:
        self.name = name

    def version_at(self, repo: Repo, revision: str) -> Version:
        """The version its version file declares at a git revision."""
        try:
            text = self._read_version(repo.git.show(f"{revision}:{self._version_file}"))
        except (GitCommandError, ValueError, KeyError, TypeError) as error:
            raise UnreadableVersionError(self.name, revision) from error
        return Version.parse(text)

    @property
    @abstractmethod
    def _version_file(self) -> str: ...

    @abstractmethod
    def _read_version(self, manifest: str) -> str: ...


class PythonLibrary(Library):
    @property
    @override
    def _version_file(self) -> str:
        return f"{self.name}/pyproject.toml"

    @override
    def _read_version(self, manifest: str) -> str:
        return str(tomllib.loads(manifest)["project"]["version"])


class NpmLibrary(Library):
    @property
    @override
    def _version_file(self) -> str:
        return f"{self.name}/package.json"

    @override
    def _read_version(self, manifest: str) -> str:
        return str(json.loads(manifest)["version"])


LIBRARIES: tuple[Library, ...] = (
    PythonLibrary("markcom"),
    NpmLibrary("markcom-web-config"),
    NpmLibrary("markcom-i18n"),
)
