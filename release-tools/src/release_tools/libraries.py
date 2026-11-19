import json
import tomllib
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar, cast, override

import tomlkit
from git import GitCommandError, Repo
from tomlkit.items import AoT, Table

from release_tools.versions import Version

# npm runs these when it packs, publishes or installs; the rest never reach a user
SHIPPED_NPM_SCRIPTS = frozenset(
    {"build", "prepare", "prepack", "prepublishOnly", "preinstall", "install", "postinstall"}
)


class UnreadableVersionError(RuntimeError):
    def __init__(self, library: str, revision: str) -> None:
        super().__init__(f"could not read {library}'s version at {revision}")


class Library(ABC):
    """One library this repository releases, in the folder named after it. A release follows a
    change to its code (its `src` folder and any `extra_code` files, tests excluded) or to its
    install manifest."""

    manifest: ClassVar[str]
    tests: ClassVar[str]

    def __init__(self, name: str, extra_code: tuple[str, ...] = ()) -> None:
        self.name = name
        # git pathspecs from the repository root; an exclude pattern's * also matches /
        self._code = (
            *(f"{name}/{path}" for path in ("src", *extra_code)),
            f":(exclude){name}/{self.tests}",
        )

    def tag(self, version: Version) -> str:
        return f"{self.name}-v{version}"

    def version_at(self, repo: Repo, revision: str) -> Version:
        try:
            text = self._version(self._manifest_at(repo, revision))
        except (GitCommandError, ValueError, KeyError, TypeError) as error:
            raise UnreadableVersionError(self.name, revision) from error
        return Version.parse(text)

    def latest_release(self, repo: Repo) -> Version | None:
        """The highest version tagged, or None before its first release."""
        prefix = f"{self.name}-v"
        tags = [tag.name for tag in repo.tags if tag.name.startswith(prefix)]
        return max((Version.parse(tag.removeprefix(prefix)) for tag in tags), default=None)

    def release_inputs_changed(self, repo: Repo, since: str, until: str) -> bool:
        before = self._install_manifest(self._manifest_at(repo, since))
        after = self._install_manifest(self._manifest_at(repo, until))
        changed_code = repo.git.diff("--name-only", since, until, "--", *self._code)
        return before != after or bool(changed_code)

    def _manifest_at(self, repo: Repo, revision: str) -> str:
        return str(repo.git.show(f"{revision}:{self.name}/{self.manifest}"))

    @abstractmethod
    def _version(self, manifest: str) -> str: ...

    @abstractmethod
    def _install_manifest(self, manifest: str) -> str:
        """The parts of the manifest an install reads, without the version, as sorted JSON."""

    @abstractmethod
    def write_version(self, root: Path, version: Version) -> None:
        """Writes the version into its manifest and lock file in the working tree at `root`."""


class PythonLibrary(Library):
    manifest = "pyproject.toml"
    tests = "*_test.py"

    @override
    def _version(self, manifest: str) -> str:
        return str(tomllib.loads(manifest)["project"]["version"])

    @override
    def _install_manifest(self, manifest: str) -> str:
        data = tomllib.loads(manifest)
        del data["project"]["version"]
        hatch = data.get("tool", {}).get("hatch")
        return json.dumps([data["project"], data["build-system"], hatch], sort_keys=True)

    @override
    def write_version(self, root: Path, version: Version) -> None:
        pyproject_path = root / self.name / self.manifest
        pyproject = tomlkit.parse(pyproject_path.read_text(encoding="utf-8"))
        cast("Table", pyproject["project"])["version"] = str(version)
        pyproject_path.write_text(tomlkit.dumps(pyproject), encoding="utf-8")
        lock_path = root / self.name / "uv.lock"
        lock = tomlkit.parse(lock_path.read_text(encoding="utf-8"))
        for package in cast("AoT", lock["package"]):
            if package["name"] == self.name:
                package["version"] = str(version)
        lock_path.write_text(tomlkit.dumps(lock), encoding="utf-8")


class NpmLibrary(Library):
    manifest = "package.json"
    tests = "*.test.ts"

    @override
    def _version(self, manifest: str) -> str:
        return str(json.loads(manifest)["version"])

    @override
    def _install_manifest(self, manifest: str) -> str:
        data = json.loads(manifest)
        scripts = data.pop("scripts", {})
        for key in ("version", "devDependencies", "overrides"):
            data.pop(key, None)
        data["scripts"] = {key: scripts[key] for key in scripts if key in SHIPPED_NPM_SCRIPTS}
        return json.dumps(data, sort_keys=True)

    @override
    def write_version(self, root: Path, version: Version) -> None:
        for path in (root / self.name / self.manifest, root / self.name / "package-lock.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            data["version"] = str(version)
            # package-lock.json repeats the version in its root package entry
            if "packages" in data:
                data["packages"][""]["version"] = str(version)
            # npm's own formatting: two-space indent, final newline
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


LIBRARIES: tuple[Library, ...] = (
    PythonLibrary("markcom"),
    # projects extend these two files directly, so they are web-config's code
    NpmLibrary("markcom-web-config", extra_code=("tsconfig.json", "prettier.json")),
    NpmLibrary("markcom-i18n"),
)
