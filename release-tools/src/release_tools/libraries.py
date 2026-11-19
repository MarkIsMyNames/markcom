import json
import tomllib
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import override

import tomlkit
from git import GitCommandError, Repo
from tomlkit.items import AoT, Table

from release_tools.versions import Version

type Json = dict[str, Json] | list[Json] | str | int | float | bool | None

# npm runs these when it packs, publishes or installs; the rest never reach a user
SHIPPED_NPM_SCRIPTS = frozenset(
    {"build", "prepare", "prepack", "prepublishOnly", "preinstall", "install", "postinstall"}
)


class UnreadableVersionError(RuntimeError):
    def __init__(self, library: str, revision: str) -> None:
        super().__init__(f"could not read {library}'s version at {revision}")


class Library(ABC):
    """One library this repository releases, in the folder named after it. A release follows a
    change to its code (`code_paths`, git pathspecs) or to its install manifest."""

    def __init__(self, name: str, code_paths: tuple[str, ...]) -> None:
        self.name = name
        self.code_paths = code_paths

    @property
    def tag_prefix(self) -> str:
        return f"{self.name}-v"

    def tag(self, version: Version) -> str:
        return f"{self.tag_prefix}{version}"

    def version_at(self, repo: Repo, revision: str) -> Version:
        """The version its version file declares at a git revision."""
        try:
            text = self._read_version(repo.git.show(f"{revision}:{self._manifest_file}"))
        except (GitCommandError, ValueError, KeyError, TypeError) as error:
            raise UnreadableVersionError(self.name, revision) from error
        return Version.parse(text)

    def latest_release(self, repo: Repo) -> Version | None:
        """The highest version tagged, or None before its first release."""
        versions = [
            Version.parse(tag.name.removeprefix(self.tag_prefix))
            for tag in repo.tags
            if tag.name.startswith(self.tag_prefix)
        ]
        return max(versions, default=None)

    def release_inputs_changed(self, repo: Repo, since: str, until: str) -> bool:
        if self._install_manifest(repo, since) != self._install_manifest(repo, until):
            return True
        return bool(repo.git.diff("--name-only", since, until, "--", *self.code_paths))

    def _install_manifest(self, repo: Repo, revision: str) -> str:
        manifest = self._install_parts(repo.git.show(f"{revision}:{self._manifest_file}"))
        return json.dumps(manifest, sort_keys=True)

    @abstractmethod
    def write_version(self, root: Path, version: Version) -> None:
        """Writes the version into its manifest and lock file in the working tree at `root`."""

    @property
    @abstractmethod
    def _manifest_file(self) -> str: ...

    @abstractmethod
    def _read_version(self, manifest: str) -> str: ...

    @abstractmethod
    def _install_parts(self, manifest: str) -> Json:
        """The parts of the manifest an install reads, without the version."""


def _table(container: tomlkit.TOMLDocument | Table, key: str) -> Table:
    item = container[key]
    if not isinstance(item, Table):
        message = f"[{key}] is not a TOML table"
        raise TypeError(message)
    return item


class PythonLibrary(Library):
    @property
    @override
    def _manifest_file(self) -> str:
        return f"{self.name}/pyproject.toml"

    @override
    def _read_version(self, manifest: str) -> str:
        return str(tomllib.loads(manifest)["project"]["version"])

    @override
    def _install_parts(self, manifest: str) -> Json:
        data = tomllib.loads(manifest)
        project = {key: value for key, value in data["project"].items() if key != "version"}
        return [project, data["build-system"], data.get("tool", {}).get("hatch")]

    @override
    def write_version(self, root: Path, version: Version) -> None:
        pyproject_path = root / self._manifest_file
        pyproject = tomlkit.parse(pyproject_path.read_text(encoding="utf-8"))
        _table(pyproject, "project")["version"] = str(version)
        pyproject_path.write_text(tomlkit.dumps(pyproject), encoding="utf-8")
        lock_path = root / self.name / "uv.lock"
        lock = tomlkit.parse(lock_path.read_text(encoding="utf-8"))
        packages = lock["package"]
        if not isinstance(packages, AoT):
            message = f"{lock_path} has no [[package]] tables"
            raise TypeError(message)
        for package in packages:
            if package["name"] == self.name:
                package["version"] = str(version)
        lock_path.write_text(tomlkit.dumps(lock), encoding="utf-8")


def _rewrite_json(path: Path, change: Callable[[dict[str, Json]], None]) -> None:
    """Edits a JSON file, keeping npm's formatting: two-space indent, final newline."""
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


class NpmLibrary(Library):
    @property
    @override
    def _manifest_file(self) -> str:
        return f"{self.name}/package.json"

    @override
    def _read_version(self, manifest: str) -> str:
        return str(json.loads(manifest)["version"])

    @override
    def _install_parts(self, manifest: str) -> Json:
        data = json.loads(manifest)
        parts = {
            key: value
            for key, value in data.items()
            if key not in {"version", "devDependencies", "overrides", "scripts"}
        }
        scripts = data.get("scripts", {})
        parts["scripts"] = {key: scripts[key] for key in scripts if key in SHIPPED_NPM_SCRIPTS}
        return parts

    @override
    def write_version(self, root: Path, version: Version) -> None:
        text = str(version)

        def set_lock(lock: dict[str, Json]) -> None:
            lock["version"] = text
            packages = lock["packages"]
            if not isinstance(packages, dict) or not isinstance(packages[""], dict):
                message = f"{self.name}'s package-lock.json has no root package entry"
                raise TypeError(message)
            packages[""]["version"] = text

        _rewrite_json(root / self._manifest_file, lambda manifest: manifest.update(version=text))
        _rewrite_json(root / self.name / "package-lock.json", set_lock)


LIBRARIES: tuple[Library, ...] = (
    PythonLibrary("markcom", ("markcom/src", ":(exclude)*_test.py")),
    NpmLibrary(
        "markcom-web-config",
        (
            "markcom-web-config/src",
            ":(exclude)*.test.ts",
            # projects extend these two directly, so they are its code
            "markcom-web-config/tsconfig.json",
            "markcom-web-config/prettier.json",
        ),
    ),
    NpmLibrary("markcom-i18n", ("markcom-i18n/src", ":(exclude)*.test.ts")),
)
